"""검사된 공개 수치지도와 관측 강우를 불변 지도·모델 버전으로 연결."""
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

from shapely.geometry import Polygon, MultiPolygon
import audit_spatial_sources as audit
from prepare_topography_candidates import read_sources

ROOT = audit.ROOT
MAP_ID = 'seongsu-ngii-2025-v2'
LEGACY = ['seongsu-lab.json', 'seongsu-421-20240622.json',
          'seongsu-421-20240702.json', 'seongsu-421-20240718.json']
LEGACY_HASHES = ['3af2362021b1678b743a54d82ec1cd1e40cc3b1bfaf594a39858843b35fafaee',
                 'eb5b6e36c3a161f5f4ea4b61921a5960cf9104b0c899d3afb551a87d4bc2d3f3',
                 '00991b8d0823ac4d977a8e3a6f16c240720e9334396edccec7e4aa3a13dffbff',
                 'fff031781cebc7f1b1f8e6cd0ed284c2166f688d80a2c70a2e4c24ee2df438c3']
CANDIDATE_HASH = 'd879febb289cd101caaec9758a2e5df078ed903f1f1b8983b37fa1a7b0d485ec'


def payload(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n').encode()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def polygons(geometry, origin):
    if geometry.is_empty:
        return []
    if not isinstance(geometry, (Polygon, MultiPolygon)):
        raise audit.SpatialDataError('지도 면 도형 필요')
    parts = [geometry] if isinstance(geometry, Polygon) else geometry.geoms
    return [[[[x-origin[0], y-origin[1]] for x,y in ring.coords]
             for ring in [part.exterior, *part.interiors]] for part in parts]


def height(floors):
    return floors*3.2 if floors else 9


def make_map(records, study, candidates, registry):
    origin = candidates['originProjected']
    features = []
    for item in records['buildings']:
        geometry, floors = item['geometry'], item['attributes']['aboveGroundFloors']
        center = geometry.representative_point()
        features.append({'id': item['id'], 'kind': 'building', 'name': '',
                         'polygons': polygons(geometry, origin),
                         'heightM': height(floors),
                         'heightSource': 'LEVELS_ESTIMATE' if floors else 'VISUAL_ASSUMPTION',
                         'displayAreaM2': geometry.area,
                         'center': [center.x-origin[0], center.y-origin[1]],
                         'aboveGroundFloors': floors})
    for kind in ('roads', 'railways', 'bridges'):
        for item in records[kind]:
            geometry = item['geometry'].intersection(study)
            if geometry.area <= 0:
                continue
            features.append({'id': kind+':'+item['id'], 'kind': 'transport',
                             'transportType': kind, 'polygons': polygons(geometry, origin)})
    minx,miny,maxx,maxy = study.bounds
    return {'id': MAP_ID, 'title': '성수 · 수치지형도 2025',
            'subtitle': '국토지리정보원 1:1,000 공개 수치지도',
            'origin': [(registry['boundsWgs84'][0]+registry['boundsWgs84'][2])/2,
                       (registry['boundsWgs84'][1]+registry['boundsWgs84'][3])/2],
            'originProjected': origin, 'coordinateSystem': 'EPSG:5186_LOCAL_TRANSLATION',
            'bounds': registry['boundsWgs84'],
            'widthM': 2*max(abs(minx-origin[0]), abs(maxx-origin[0])),
            'depthM': 2*max(abs(miny-origin[1]), abs(maxy-origin[1])),
            'validationLevel': 'DRAFT', 'officialEvaluationAvailable': False,
            'sourceHash': candidates['registrySha256'], 'features': features,
            'attribution': '국토지리정보원 · 2025 수치지도 · 공공누리 제1유형',
            'licenseUrl': registry['licenseEvidenceUrl'],
            'limitations': ['2025 지도 형상에서 과거 관측 강우를 재생하며 당시 현장을 재현하지 않음',
                            '지면 평탄화; 층수×3.2m 또는 9m 높이는 시각화 가정',
                            '건물 원형 보존·교통 면은 표시 영역으로 절단; 교량 고도 미확인',
                            '설치 적합성·지붕 하중·배수 연결·현장 유출 미검증']}


def make_models(candidates, map_hash):
    cells = []
    for candidate in candidates['cells']:
        roof = candidate['kind'] == 'ROOF'
        area = candidate['areaM2']
        c = {key: candidate[key] for key in ('id', 'kind', 'coordinates', 'center', 'areaM2', 'areaEvidence', 'siteEligibility', 'sourceIds')}
        c.update({'name': ('옥상 후보 ' if roof else '도로 실험 구역 ')+candidate['id'][1:],
                  'maxAreaM2': math.floor(area*(.6 if roof else .8)*100)/100,
                  'heightM': height(candidate['attributes'].get('aboveGroundFloors')) if roof else .12,
                  'allowedTypes': ['GREEN_ROOF'] if roof else ['RAIN_GARDEN', 'PERMEABLE_PAVEMENT'],
                  'eligibilityEvidence': 'UNKNOWN_DESIGN_CAP_NOT_SITE_APPROVED'})
        if roof:
            c['buildingId'] = candidate['sourceIds'][0]
        cells.append(c)
    output = []
    for filename, expected in zip(LEGACY, LEGACY_HASHES):
        original = (ROOT/'data/models'/filename).read_bytes()
        if sha(original) != expected:
            raise audit.SpatialDataError('이전 모델 원문 불일치')
        model = json.loads(original)
        rain = model['rainfall']
        local_date = datetime.fromisoformat(rain['start']).astimezone(ZoneInfo('Asia/Seoul')).date().isoformat()
        identifier = f"seongsu-ngii-v2-{rain['stationId']}-{local_date.replace('-', '')}"
        model.update({'id': identifier, 'title': '성수 수치지형도 2025 · '+rain['stationName']+' '+local_date,
                      'mapId': MAP_ID, 'mapTitle': '수치지형도 2025', 'mapSnapshotHash': map_hash,
                      'geometrySourceHash': candidates['registrySha256'], 'candidateSnapshotHash': CANDIDATE_HASH,
                      'cells': copy.deepcopy(cells), 'maxPlacements': len(cells),
                      'geometryEvidence': 'NGII_2025_PROJECTED_FOOTPRINT_AND_DESIGN_GRID',
                      'geometryModelGeneratorSha256': audit.digest(Path(__file__)),
                      'geometryPolicy': {'roofAreaCapFraction': .6, 'groundAreaCapFraction': .8,
                                         'evidence': 'ASSUMED_DESIGN_LIMIT_NOT_SURVEYED'}})
        model['assumptions'] += ['2025 공개 수치지도 형상에서 과거 강우 재생; 강우 당시 현장 재현 아님',
                                '옥상 60%·도로 격자 80% 면적 상한은 설계 가정; 설치 적합성 UNKNOWN',
                                '면적은 EPSG:5186 투영 경계; 높이는 시각화 가정이며 수문 입력 제외',
                                'DEM·토지피복·관망·토양 보정 미반영; 교량·철도·건물과 겹치는 지상 후보 제외']
        output.append((identifier+'.json', payload(model)))
    return output


def write(path, data, check, mutable=False):
    if path.is_symlink():
        raise audit.SpatialDataError('출력 링크 거부')
    if path.exists() and path.read_bytes() == data:
        return
    if check or (path.exists() and not mutable):
        raise audit.SpatialDataError(f'고정 산출물 불일치: {path.name}')
    path.write_bytes(data)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    candidate_path = ROOT/'data/derived/seongsu-topography-candidates-v2.json'
    if audit.digest(candidate_path) != CANDIDATE_HASH:
        raise audit.SpatialDataError('검사된 후보 원문 불일치')
    candidates = json.loads(candidate_path.read_text())
    registry = json.loads((ROOT/'data/manifests/seongsu-topography-sources.json').read_text())
    if candidates['registrySha256'] != audit.digest(ROOT/'data/manifests/seongsu-topography-sources.json'):
        raise audit.SpatialDataError('원본 목록 불일치')
    records, study, _, _ = read_sources(registry)
    snapshot = make_map(records, study, candidates, registry)
    map_bytes = payload(snapshot)
    map_file = 'seongsu-ngii-v2.json'
    write(ROOT/'frontend/public/data'/map_file, map_bytes, args.check)
    generated = make_models(candidates, sha(map_bytes))
    entries = []
    for name, expected in zip(LEGACY, LEGACY_HASHES):
        original = json.loads((ROOT/'data/models'/name).read_text())
        entries.append({'id': original['id'], 'file': name, 'sha256': expected})
    for name, data in generated:
        for folder in ('data/models', 'backend/src/main/resources/models'):
            write(ROOT/folder/name, data, args.check)
        entries.append({'id': json.loads(data)['id'], 'file': name, 'sha256': sha(data)})
    catalog = payload({'schemaVersion': 1, 'defaultModelHash': entries[-1]['sha256'], 'models': entries})
    for folder in ('data/models', 'backend/src/main/resources/models'):
        write(ROOT/folder/'catalog.json', catalog, args.check, mutable=True)
    legacy_path = ROOT/'frontend/public/data/seongsu.json'
    legacy = json.loads(legacy_path.read_text())
    maps = {'schemaVersion': 1, 'maps': [
        {'id': legacy['id'], 'file': 'seongsu.json', 'sha256': audit.digest(legacy_path),
         'modelHashes': LEGACY_HASHES},
        {'id': MAP_ID, 'file': map_file, 'sha256': sha(map_bytes),
         'modelHashes': [e['sha256'] for e in entries[4:]]}]}
    write(ROOT/'frontend/public/data/maps.json', payload(maps), args.check)
    print(json.dumps({'models': len(entries), 'buildings': len(records['buildings']),
                      'mapHash': sha(map_bytes), 'defaultModelHash': entries[-1]['sha256']}))


if __name__ == '__main__':
    main()
