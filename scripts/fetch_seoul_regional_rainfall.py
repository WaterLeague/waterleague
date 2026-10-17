"""보관된 대표 블록과 과거 지점 목록으로 인근 AWS 분 원본 수집."""
import copy
import hashlib
import json
import math
import os
import sys
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import build_opener

import pyproj

from fetch_kma import NoRedirect
from local_config import ROOT, load
from prepare_rainfall_catalog import statistics

sys.path.insert(0, str(ROOT/'simulation'))
from waterleague_sim.ingestion.kma import normalize, KST
from waterleague_sim.ingestion.rainfall import RainfallQualityError

WINDOWS = [('202406220001', '202406222359'), ('202407020001', '202407022359'),
           ('202407180500', '202407182359')]
STATIONS_URL = 'https://apihub.kma.go.kr/api/typ01/url/stn_inf.php'
RAIN_URL = 'https://apihub.kma.go.kr/api/typ01/cgi-bin/url/nph-aws2_min'
STATION_DOC = 'https://apihub.kma.go.kr/apiList.do?seqApi=2&seqApiSub=317'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def save_json(path, value):
    data = (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n').encode()
    if path.exists() and path.read_bytes() != data:
        raise ValueError('기존 파생자료 덮어쓰기 거부: '+path.name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def fetch(stem, endpoint, parameters, key, limit=4000000):
    raw = ROOT/'data/raw'/f'{stem}.txt'
    manifest = ROOT/'data/manifests'/f'{stem}.json'
    if raw.exists() or manifest.exists():
        if not raw.exists() or not manifest.exists():
            raise ValueError('원본·manifest 쌍 확인 필요: '+stem)
        data = raw.read_bytes()
        saved = json.loads(manifest.read_text())
        if saved['sha256'] != digest(data) or saved['parameters'] != parameters or saved['endpoint'] != endpoint:
            raise ValueError('보관 원본 검증 실패: '+stem)
        return data
    for attempt in range(2):
        try:
            with build_opener(NoRedirect()).open(endpoint+'?'+urlencode(parameters | {'authKey': key}), timeout=45) as response:
                data = response.read(limit+1)
            if key.encode() in data:
                raise SystemExit('비밀값이 포함된 응답 저장 거부')
            if len(data) > limit or b'#START7777' not in data or b'#7777END' not in data:
                raise ValueError('원본 형식 검사 실패: '+stem)
            break
        except HTTPError as error:
            if error.code in (401, 403) or attempt:
                raise ValueError(f'기상청 HTTP {error.code}: '+stem) from None
        except Exception:
            if attempt:
                raise ValueError('기상청 원본 수집 실패: '+stem) from None
    raw.parent.mkdir(parents=True, exist_ok=True)
    raw.write_bytes(data)
    save_json(manifest, {'provider': '기상청', 'endpoint': endpoint, 'parameters': parameters,
                        'acquiredAt': datetime.now(timezone.utc).isoformat(), 'sha256': digest(data),
                        'bytes': len(data), 'sourceTimezone': 'Asia/Seoul'})
    return data


def stations_at(time, key):
    stem = 'kma-stations-aws-'+time
    data = fetch(stem, STATIONS_URL, {'inf': 'AWS', 'stn': '', 'tm': time, 'help': '1'}, key)
    stations = {}
    for line in data.decode('euc-kr').splitlines():
        if not line.strip() or line.startswith('#'):
            continue
        fields = line.split()
        if len(fields) < 13 or not fields[0].isdigit() or fields[0] in stations:
            raise ValueError('지점 목록 형식 오류')
        lon, lat, altitude = [float(fields[i]) for i in (1, 2, 4)]
        if not all(math.isfinite(v) for v in (lon, lat, altitude)) or not 124 < lon < 132 or not 32 < lat < 40:
            raise ValueError('지점 좌표 오류')
        stations[fields[0]] = {'provider': '기상청', 'stationId': fields[0], 'stationName': fields[8],
                              'longitude': lon, 'latitude': lat, 'elevationM': altitude,
                              'crs': 'EPSG:4326', 'requestedTimeKst': time, 'sourceSha256': digest(data),
                              'sourceManifest': stem+'.json', 'sourceUrl': STATION_DOC,
                              'historicalValidity': 'API_TIME_QUERY_CONFIRMED',
                              'limitation': '관측 창 양 끝 시점 API 좌표 확인; 전체 이전 이력·부지 강우 대표성 미검증'}
    if not stations:
        raise ValueError('지점 목록 없음')
    return stations


def event(station, start, end, key):
    station_id = station['stationId']
    stem = f'kma-{station_id}-{start}-{end}'
    data = fetch(stem, RAIN_URL, {'tm1': start, 'tm2': end, 'stn': station_id, 'disp': '0', 'help': '1'}, key)
    rows, total = normalize(data.decode('utf-8'))
    expected = [datetime.strptime(t, '%Y%m%d%H%M').replace(tzinfo=KST).astimezone(timezone.utc) for t in (start, end)]
    if rows[0].start != expected[0] or rows[-1].end != expected[1] or any(r.station_id != station_id for r in rows):
        raise RainfallQualityError('요청 시간·관측소 불일치')
    if total <= 0:
        raise RainfallQualityError('강우 없는 관측 창')
    template = json.loads((ROOT/'data/derived/rainfall'/f'kma-421-{start}-{end}.json').read_text())
    result = copy.deepcopy(template)
    result.update({'id': stem+'-historical-v1', 'stationId': station_id, 'stationName': station['stationName'],
                   'depthsMm': [float(r.depth_mm) for r in rows], 'totalDepthMm': float(total),
                   'sourceHash': digest(data), 'sourceManifest': stem+'.json', 'stationMetadata': station,
                   'windowStatistics': statistics(rows),
                   'limitations': [s.replace('현장 강우 대표성·관측소 2024년 위치 이력 미검증',
                       '관측 창 양 끝의 지점 좌표 확인; 현장 강우 대표성·전체 이전 이력 미검증') for s in template['limitations']]})
    result.pop('stationDistanceKm', None)
    result.pop('stationDistanceEvidence', None)
    save_json(ROOT/'data/derived/rainfall'/f"{result['id']}.json", result)
    return result


def main():
    load()
    key = os.environ.get('KMA_API_KEY')
    if not key:
        raise SystemExit('.env.local KMA_API_KEY 필요')
    registry_path = ROOT/'data/manifests/seoul-play-v1.json'
    regions = json.loads(registry_path.read_text())['regions']
    geod = pyproj.Geod(ellps='WGS84')
    selections = []
    for start, end in WINDOWS:
        stations, end_stations = stations_at(start, key), stations_at(end, key)
        selected = {}
        for region in regions:
            snapshot = ROOT/'frontend/public/data'/region['mapFile']
            if digest(snapshot.read_bytes()) != region['mapSha256']:
                raise ValueError('구역 지도 해시 불일치')
            lon, lat = json.loads(snapshot.read_text())['origin']
            selected[region['mapId']] = min((geod.inv(lon, lat, s['longitude'], s['latitude'])[2]/1000, s['stationId'])
                                            for s in stations.values())
        executor = ThreadPoolExecutor(max_workers=3)
        events = {}
        for distance, station_id in selected.values():
            station = copy.deepcopy(stations[station_id])
            last = end_stations.get(station_id)
            if distance <= 10 and last and all(last[k] == station[k] for k in ('longitude', 'latitude', 'elevationM')):
                station.update({'endTimeKst': end, 'endSourceSha256': last['sourceSha256'],
                                'endSourceManifest': last['sourceManifest']})
                if station_id not in events:
                    events[station_id] = executor.submit(event, station, start, end, key)
        for region in regions:
            distance, station_id = selected[region['mapId']]
            station = copy.deepcopy(stations[station_id])
            selection = {'districtId': region['districtId'], 'districtName': region['districtName'],
                         'mapId': region['mapId'], 'startKst': start, 'endKst': end,
                         'stationId': station_id, 'stationName': station['stationName'],
                         'stationDistanceKm': round(distance, 3), 'status': 'REJECTED'}
            try:
                if distance > 10:
                    raise ValueError('인근 관측소 10 km 상한 초과')
                last = end_stations.get(station_id)
                if not last or any(last[k] != station[k] for k in ('longitude', 'latitude', 'elevationM')):
                    raise ValueError('관측 창 양 끝 지점 위치 불일치')
                station['endTimeKst'] = end
                station['endSourceSha256'] = last['sourceSha256']
                station['endSourceManifest'] = last['sourceManifest']
                rain = events[station_id].result()
                selection.update({'status': 'ACCEPTED', 'rainfallId': rain['id'],
                                  'rainfallSha256': digest((ROOT/'data/derived/rainfall'/f"{rain['id']}.json").read_bytes()),
                                  'totalDepthMm': rain['totalDepthMm']})
            except (RainfallQualityError, ValueError) as error:
                selection['reason'] = str(error)
            selections.append(selection)
            print(region['districtName'], start[:8], station_id, selection['stationDistanceKm'],
                  selection['status'], selection.get('totalDepthMm', selection.get('reason')), flush=True)
        executor.shutdown(wait=True)
    report = {'schemaVersion': 1, 'selectionRule': 'NEAREST_AWS_AT_WINDOW_START_WITHIN_10KM',
              'stationLocationCheck': 'SAME_COORDINATES_AT_WINDOW_START_AND_END',
              'geometryRegistrySha256': digest(registry_path.read_bytes()),
              'collectorSha256': digest(Path(__file__).read_bytes()), 'selections': selections}
    save_json(ROOT/'data/manifests/seoul-regional-rainfall-v1.json', report)


if __name__ == '__main__':
    main()
