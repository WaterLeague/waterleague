"""직접 조회한 AWS 응답의 계산 입력 고정과 네트워크 없는 재생."""
from datetime import datetime, timedelta
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re

from waterleague_sim.engine.flood_errors import FloodModelError, require
from waterleague_sim.ingestion import live
from waterleague_sim.ingestion.rainfall import RainfallQualityError
from waterleague_sim.forcing.observed_rainfall import utc

METHOD = 'KMA_AWS_DIRECT_RESPONSE_V1'
MAX_BYTES = 32 * 1024**2


def encode(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False) + '\n').encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read_live_station(reference, start, end):
    require(isinstance(reference, dict) and set(reference) == {'stationId', 'responses'},
            'LIVE_SURFACE_REFERENCE_INVALID')
    station = reference['stationId']
    responses = reference['responses']
    require(isinstance(station, str) and re.fullmatch(r'\d{1,5}', station)
            and isinstance(responses, list) and 0 < len(responses) <= 29*1440+61,
            'LIVE_SURFACE_REFERENCE_INVALID')
    require(start.second == end.second == start.microsecond == end.microsecond == 0
            and 0 < (end-start).total_seconds() <= 29*86400, 'LIVE_SURFACE_WINDOW_INVALID')
    cursor = start - timedelta(minutes=61)
    rows, files, hashes, seen_hashes, size = {}, {}, [], set(), 0
    for response in responses:
        require(isinstance(response, dict) and set(response) == {'rawUtf8', 'metadata'}
                and isinstance(response['rawUtf8'], str), 'LIVE_SURFACE_RESPONSE_INVALID')
        raw, metadata = response['rawUtf8'].encode(), response['metadata']
        size += len(raw)
        require(len(raw) <= 4_000_000 and size <= MAX_BYTES, 'LIVE_SURFACE_RESPONSE_TOO_LARGE')
        require(isinstance(metadata, dict) and set(metadata) == {
            'provider', 'endpoint', 'parameters', 'fetchedAt', 'sha256', 'purpose'}
            and metadata['provider'] == 'KMA_AWS_DIRECT'
            and metadata['endpoint'] == live.ENDPOINT
            and metadata['purpose'] == 'SIMULATION_USED_INPUT_ONLY'
            and metadata['sha256'] == sha(raw), 'LIVE_SURFACE_SOURCE_INVALID')
        parameters = metadata['parameters']
        require(isinstance(parameters, dict) and set(parameters) == {'tm1', 'tm2', 'stn', 'disp', 'help'}
                and parameters['stn'] == station and parameters['disp'] == '0'
                and parameters['help'] == '1' and all(isinstance(parameters[k], str)
                    and re.fullmatch(r'\d{12}', parameters[k]) for k in ('tm1', 'tm2')),
                'LIVE_SURFACE_SOURCE_INVALID')
        try:
            a, b = [datetime.strptime(parameters[k], '%Y%m%d%H%M').replace(tzinfo=live.KST)
                    for k in ('tm1', 'tm2')]
            fetched = utc(metadata['fetchedAt'])
            require(a == cursor and a < b <= end and (b-a).total_seconds() <= 86400
                    and fetched >= b, 'LIVE_SURFACE_RESPONSE_CLOCK_INVALID')
            values = live.parse(raw, station, a, b)
            for at, value in values.items():
                require(at not in rows or rows[at] == value, 'LIVE_SURFACE_OVERLAPPING_RESPONSE_CHANGED')
                rows[at] = value
        except (ValueError, UnicodeError) as error:
            if isinstance(error, FloodModelError):
                raise
            raise FloodModelError('LIVE_SURFACE_SOURCE_INVALID') from None
        cursor = b
        digest = sha(raw)
        require(digest not in seen_hashes, 'LIVE_SURFACE_DUPLICATE_RESPONSE')
        hashes.append(digest)
        seen_hashes.add(digest)
        files[f'direct-aws/{digest}.txt'] = raw
        files[f'direct-aws/{digest}.json'] = encode(metadata)
    require(cursor == end, 'LIVE_SURFACE_COVERAGE_INCOMPLETE')
    try:
        observations = live.normalized(rows, start, end)
    except RainfallQualityError:
        raise FloodModelError('LIVE_SURFACE_RAIN_QUALITY_INVALID') from None
    depths = [row['depthMm'] for row in observations]
    derived = {'stationId': station, 'start': start.isoformat(), 'end': end.isoformat(),
        'depthsMm': depths, 'totalDepthMm': float(sum((Decimal(str(v)) for v in depths), Decimal(0))),
        'intervalSeconds': 60, 'sourceType': METHOD, 'sourceHashes': hashes,
        'observations': observations, 'qualityPolicy': 'COMPLETE_MINUTES_STRICT_ROLLING_CHECK',
        'derivationCodeSha256': sha(Path(live.__file__).read_bytes())}
    manifest = encode(derived)
    files[f'direct-aws/station-{station}.json'] = manifest
    # 여러 원 응답의 묶음 해시를 개별 응답의 원문 해시와 구분한다.
    return derived | {'sourceHash': sha(manifest), 'sourceHashKind': 'STATION_DERIVATION_BUNDLE'}, files


def capture(surface, station_by_triangle, start, end, key, assignment_evidence, *,
            network=None, station_by_catchment=None):
    from waterleague_sim.forcing.observed_rainfall import compile_rainfall
    require(isinstance(station_by_triangle, list) and len(station_by_triangle) == len(surface['triangles'])
            and len(station_by_triangle) == len(surface['rainfallOwner']), 'LIVE_SURFACE_ASSIGNMENT_INVALID')
    require(isinstance(assignment_evidence, str) and assignment_evidence.strip(),
            'LIVE_SURFACE_ASSIGNMENT_INVALID')
    require(all((owner == 'NETWORK' and sid is None) or (owner == 'SURFACE'
            and isinstance(sid, str) and re.fullmatch(r'\d{1,5}', sid))
            for owner, sid in zip(surface['rainfallOwner'], station_by_triangle)),
            'LIVE_SURFACE_ASSIGNMENT_INVALID')
    network_stations = set()
    if network is not None or station_by_catchment is not None:
        from waterleague_sim.forcing.live_network_rainfall import validate_network
        validate_network(network, {'startUtc':start.isoformat(), 'endUtc':end.isoformat(),
                                  'stationByCatchment':station_by_catchment})
        network_stations = set(station_by_catchment.values())
    stations = sorted({sid for sid in station_by_triangle if sid is not None} | network_stations)
    require(0 < len(stations) <= 100 and start.utcoffset() is not None and end.utcoffset() is not None
            and start.second == end.second == start.microsecond == end.microsecond == 0
            and 0 < (end-start).total_seconds() <= 29*86400, 'LIVE_SURFACE_WINDOW_INVALID')
    require(len(stations)*(end-start).total_seconds()/60 <= 100_000,
            'LIVE_SURFACE_ACQUISITION_LIMIT')
    spec = {'schemaVersion': 2, 'sourceType': METHOD, 'startUtc': start.isoformat(), 'endUtc': end.isoformat(),
            'stationByTriangle': station_by_triangle, 'assignmentEvidence': assignment_evidence, 'stations': []}
    if network_stations:
        spec['stationByCatchment'] = dict(station_by_catchment)
    size = 0
    for station in stations:
        _, sources = live.observed_forcing(station, start, end, key)
        size += sum(len(raw) for raw, _ in sources)
        require(size <= MAX_BYTES, 'LIVE_SURFACE_RESPONSE_TOO_LARGE')
        spec['stations'].append({'stationId': station, 'responses': [
            {'rawUtf8': raw.decode('utf-8'), 'metadata': metadata} for raw, metadata in sources]})
    # 조회 응답은 메모리에서 검증하고 실제 실행의 재현 디렉터리에만 저장한다.
    compile_rainfall(spec, surface, int((end-start).total_seconds()), network_stations=network_stations)
    return spec


def extend(specification, end, key):
    """이미 계산에 사용한 원 응답을 보존하고 이후 관측 구간만 조회한다."""
    from copy import deepcopy
    require(isinstance(specification,dict) and specification.get('schemaVersion')==2
            and specification.get('sourceType')==METHOD,'LIVE_SURFACE_EXTENSION_INVALID')
    start, previous = utc(specification.get('startUtc')), utc(specification.get('endUtc'))
    require(previous < end and (end-start).total_seconds()<=29*86400
            and end.second==end.microsecond==0,'LIVE_SURFACE_EXTENSION_WINDOW_INVALID')
    value=deepcopy(specification)
    require(isinstance(value.get('stations'),list) and 0<len(value['stations'])<=100,
            'LIVE_SURFACE_REFERENCE_INVALID')
    stations=set()
    total=0
    for reference in value['stations']:
        data,_=read_live_station(reference,start,previous)
        sid=data['stationId']
        require(sid not in stations,'LIVE_SURFACE_DUPLICATE_RESPONSE')
        stations.add(sid)
        total+=sum(len(r['rawUtf8'].encode()) for r in reference['responses'])
    require(len(stations)*(end-start).total_seconds()/60<=100_000 and total<=MAX_BYTES,
            'LIVE_SURFACE_ACQUISITION_LIMIT')
    for reference in value['stations']:
        cursor=previous
        while cursor<end:
            stop=min(cursor+timedelta(hours=23),end)
            raw,metadata=live.fetch_range(reference['stationId'],cursor,stop,key)
            total+=len(raw)
            require(total<=MAX_BYTES,'LIVE_SURFACE_RESPONSE_TOO_LARGE')
            reference['responses'].append({'rawUtf8':raw.decode('utf-8'),'metadata':metadata})
            cursor=stop
        read_live_station(reference,start,end)
    value['endUtc']=end.isoformat()
    return value
