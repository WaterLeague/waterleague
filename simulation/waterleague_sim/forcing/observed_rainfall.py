"""보관 AWS 원문을 재검사하는 격자별 강우 시간표. 외부 API 호출 없음."""
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path
import re

from waterleague_sim.engine.flood_errors import FloodModelError, require
from waterleague_sim.engine.swmm import ROOT
from waterleague_sim.ingestion.kma import normalize
from waterleague_sim.ingestion.rainfall import RainfallQualityError


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def utc(value):
    try:
        result = datetime.fromisoformat(value)
        require(result.utcoffset() is not None, 'OBSERVED_RAIN_TIME_INVALID')
        return result.astimezone(timezone.utc)
    except (TypeError, ValueError):
        raise FloodModelError('OBSERVED_RAIN_TIME_INVALID') from None


def _read(root, relative, expected=None):
    path = root / relative
    require(not any(p.is_symlink() for p in (path, *path.parents))
            and path.is_file() and path.stat().st_size <= 32 * 1024**2,
            'OBSERVED_RAIN_SOURCE_INVALID')
    raw = path.read_bytes()
    require(expected is None or digest(raw) == expected, 'OBSERVED_RAIN_SOURCE_HASH_MISMATCH')
    return raw


def _json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'OBSERVED_RAIN_DUPLICATE_FIELD')
            result[key] = value
        return result
    try:
        return json.loads(raw, object_pairs_hook=pairs)
    except (ValueError, UnicodeError):
        raise FloodModelError('OBSERVED_RAIN_SOURCE_INVALID') from None


def read_station(reference, root=ROOT):
    root = Path(root).resolve()
    name, expected = reference.get('file'), reference.get('sha256')
    require(isinstance(name, str) and re.fullmatch(
        r'kma-\d{1,5}-\d{12}-\d{12}-disaster-v1\.json', name)
        and isinstance(expected, str) and re.fullmatch('[a-f0-9]{64}', expected),
        'OBSERVED_RAIN_REFERENCE_INVALID')
    relative = 'data/derived/rainfall/' + name
    encoded = _read(root, relative, expected)
    data = _json(encoded)
    manifest_name = data.get('sourceManifest')
    require(isinstance(manifest_name, str) and re.fullmatch(
        r'kma-\d{1,5}-\d{12}-\d{12}\.json', manifest_name)
        and name == manifest_name.removesuffix('.json') + '-disaster-v1.json'
        and isinstance(data.get('sourceHash'), str) and re.fullmatch('[a-f0-9]{64}', data['sourceHash']),
        'OBSERVED_RAIN_REFERENCE_INVALID')
    manifest_path = 'data/manifests/' + manifest_name
    manifest_raw = _read(root, manifest_path)
    manifest = _json(manifest_raw)
    raw_path = 'data/raw/' + manifest_name.removesuffix('.json') + '.txt'
    body = _read(root, raw_path, data.get('sourceHash'))
    require(manifest.get('sha256') == digest(body) and manifest.get('bytes') == len(body)
            and data.get('quality') == 'BASIC_CHECKED' and data.get('intervalSeconds') == 60,
            'OBSERVED_RAIN_QUALITY_INVALID')
    require(isinstance(data.get('depthsMm'), list) and all(type(value) in (int, float)
            and math.isfinite(value) and value >= 0 for value in data['depthsMm']),
            'OBSERVED_RAIN_QUALITY_INVALID')
    try:
        rows, total = normalize(body.decode('utf-8'))
    except (ValueError, UnicodeError, RainfallQualityError):
        raise FloodModelError('OBSERVED_RAIN_RAW_QUALITY_INVALID') from None
    require(data.get('stationId') == rows[0].station_id
            and utc(data.get('start')) == rows[0].start and utc(data.get('end')) == rows[-1].end
            and data.get('depthsMm') == [float(row.depth_mm) for row in rows]
            and data.get('totalDepthMm') == float(total)
            and manifest.get('parameters', {}).get('stn') == rows[0].station_id,
            'OBSERVED_RAIN_DERIVATION_MISMATCH')
    return data, {relative: encoded, manifest_path: manifest_raw, raw_path: body}


@dataclass
class RainfallSchedule:
    events: list
    summary: dict
    source_files: dict

    def archive(self, directory):
        for relative, raw in self.source_files.items():
            path = directory / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        (directory / 'rainfall-summary.json').write_text(
            json.dumps(self.summary, ensure_ascii=False, allow_nan=False, indent=2) + '\n')


def compile_rainfall(spec, surface, duration_seconds, root=ROOT):
    require(isinstance(spec, dict) and spec.get('schemaVersion') == 1
            and isinstance(spec.get('assignmentEvidence'), str) and spec['assignmentEvidence'].strip(),
            'OBSERVED_RAIN_SPECIFICATION_INVALID')
    start, end = utc(spec.get('startUtc')), utc(spec.get('endUtc'))
    duration = (end - start).total_seconds()
    require(type(duration_seconds) is int and 0 < duration_seconds <= 60 * 100_000
            and duration == duration_seconds and duration_seconds % 60 == 0,
            'OBSERVED_RAIN_WINDOW_INVALID')
    assignments = spec.get('stationByTriangle')
    owners, triangles, vertices = (surface.get(k) for k in ('rainfallOwner', 'triangles', 'verticesM'))
    require(isinstance(assignments, list) and isinstance(owners, list) and isinstance(triangles, list)
            and 0 < len(assignments) == len(owners) == len(triangles) <= 200_000,
            'OBSERVED_RAIN_ASSIGNMENT_INVALID')
    areas = {}
    for index, (owner, station) in enumerate(zip(owners, assignments)):
        require(owner in ('SURFACE', 'NETWORK') and
                ((owner == 'NETWORK' and station is None) or (owner == 'SURFACE'
                 and isinstance(station, str) and re.fullmatch(r'\d{1,5}', station))),
                'OBSERVED_RAIN_OWNERSHIP_INVALID')
        try:
            require(isinstance(triangles[index], list) and len(triangles[index]) == 3
                    and all(type(i) is int and 0 <= i < len(vertices) for i in triangles[index]),
                    'OBSERVED_RAIN_MESH_INVALID')
            a, b, c = [vertices[i] for i in triangles[index]]
            area = ((b[0]-a[0])*(c[1]-a[1]) - (b[1]-a[1])*(c[0]-a[0])) / 2
        except (TypeError, ValueError, IndexError):
            raise FloodModelError('OBSERVED_RAIN_MESH_INVALID') from None
        require(math.isfinite(area) and area > 0, 'OBSERVED_RAIN_MESH_INVALID')
        if station is not None:
            areas.setdefault(station, []).append(area)
    areas = {key: math.fsum(value) for key, value in areas.items()}
    references = spec.get('stations')
    require(isinstance(references, list) and 0 < len(references) <= 100,
            'OBSERVED_RAIN_STATIONS_INVALID')
    stations, source_files, depths, summaries = {}, {}, {}, []
    count = duration_seconds // 60
    for reference in references:
        require(isinstance(reference, dict), 'OBSERVED_RAIN_REFERENCE_INVALID')
        data, files = read_station(reference, root)
        sid = data['stationId']
        require(sid not in stations, 'OBSERVED_RAIN_DUPLICATE_STATION')
        a, b = utc(data['start']), utc(data['end'])
        offset = (start - a).total_seconds()
        require(a <= start < end <= b and offset % 60 == 0, 'OBSERVED_RAIN_COVERAGE_INCOMPLETE')
        stations[sid], source_files = data, source_files | files
        depths[sid] = data['depthsMm'][int(offset // 60):int(offset // 60) + count]
    require(set(stations) == set(areas), 'OBSERVED_RAIN_ASSIGNMENT_INCOMPLETE')
    events, previous = [], None
    for index in range(count):
        rates = {sid: float(Decimal(str(depths[sid][index])) * 60) for sid in sorted(stations)}
        if rates != previous:
            events.append({'timeMilliseconds': index * 60_000, 'ratesMmHByStation': rates})
        previous = rates
    for sid in sorted(stations):
        total = sum((Decimal(str(value)) for value in depths[sid]), Decimal(0))
        summaries.append({'stationId': sid, 'surfaceAreaM2': areas[sid], 'depthMm': float(total),
                          'expectedVolumeM3': float(total) * areas[sid] / 1000,
                          'sourceSha256': stations[sid]['sourceHash']})
    summary = {'schemaVersion': 1, 'method': 'OBSERVED_MINUTE_DEPTH_UNIFORM_WITHIN_INTERVAL',
               'startUtc': start.isoformat(), 'endUtc': end.isoformat(),
               'durationSeconds': duration_seconds, 'observedIntervalCount': count,
               'rateChangeCount': len(events), 'stations': summaries,
               'expectedSurfaceRainfallM3': math.fsum(s['expectedVolumeM3'] for s in summaries),
               'assignmentEvidence': spec['assignmentEvidence'],
               'specificationSha256': digest(json.dumps(spec, sort_keys=True, allow_nan=False).encode()),
               'sourceFiles': {path: digest(raw) for path, raw in source_files.items()},
               'adapterSha256': digest(Path(__file__).read_bytes()),
               'limitations': ['분 내부 일정 강도 가정; 초 단위 실측 아님',
                   '관측소→격자 배정은 명시한 공간 모형; 격자별 현장 관측 아님',
                   '관측 창 밖 외삽·무강우 보간 없음; 지형·관망·경계 검증과 별개']}
    return RainfallSchedule(events, summary, source_files)


def require_network_clock(network, spec):
    options, section = {}, ''
    for line in network['inputText'].splitlines():
        fields = line.split(';', 1)[0].split()
        if fields and fields[0].startswith('['):
            section = fields[0].upper()
        elif fields and section == '[OPTIONS]' and len(fields) == 2:
            options[fields[0].upper()] = fields[1]
    try:
        start = datetime.strptime(options['START_DATE'] + ' ' + options['START_TIME'],
                                  '%m/%d/%Y %H:%M:%S').replace(tzinfo=timezone.utc)
    except (KeyError, ValueError):
        raise FloodModelError('OBSERVED_RAIN_NETWORK_CLOCK_INVALID') from None
    require(network.get('timeZone') == 'UTC' and start == utc(spec['startUtc']),
            'OBSERVED_RAIN_NETWORK_CLOCK_MISMATCH')
