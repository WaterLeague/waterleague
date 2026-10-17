"""보관된 서울 공개 도형에서 구별 비교 실험 지도와 관측 강우 모델 생성."""
import copy
import hashlib
import json
import math
from pathlib import Path

import pyproj
import shapely
from shapely.geometry import Polygon, box, shape
from shapely.strtree import STRtree

from prepare_seoul_city import ROOT, SOURCE, PBF_HASH, SOURCE_URL, ORIGIN, height, digest

EVENTS = ['20240622', '20240702', '20240718']
HARD_SURFACES = {'asphalt', 'concrete', 'paved', 'paving_stones', 'sett', 'cobblestone'}
EXCLUDED_SURFACES = {'unpaved', 'gravel', 'ground', 'sand', 'clay', 'dirt', 'grass', 'dirt/sand'}


def payload(value):
    return (json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)+'\n').encode()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write(path, data, mutable=False):
    if path.is_symlink():
        raise ValueError('출력 링크 거부')
    if path.exists() and path.read_bytes() == data:
        return
    if path.exists() and not mutable:
        raise ValueError('기존 공간 버전 덮어쓰기 거부: '+path.name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def local_polygons(g, origin):
    parts = [g] if g.geom_type == 'Polygon' else g.geoms
    return [[[[x-origin[0], y-origin[1]] for x, y in ring.coords]
             for ring in [p.exterior, *p.interiors]] for p in parts]


def source_id(p):
    return 'relation/'+p['osm_id'] if p.get('osm_id') else 'way/'+p['osm_way_id']


def ground_cells(parking, buildings, tree):
    g = parking['geometry']
    minx, miny, maxx, maxy = g.bounds
    point = g.representative_point()
    candidates = []
    for x in range(math.ceil(minx/5), math.floor(maxx/5)):
        for y in range(math.ceil(miny/5), math.floor(maxy/5)):
            cell = box(x*5, y*5, x*5+5, y*5+5)
            if g.covers(cell) and len(tree.query(cell, predicate='intersects')) == 0:
                candidates.append(cell)
    candidates.sort(key=lambda c: (c.centroid.distance(point), c.bounds))
    selected = []
    for cell in candidates:
        if all(cell.centroid.distance(c.centroid) >= 10 for c in selected):
            selected.append(cell)
        if len(selected) == 5:
            break
    return selected


def read_shapes():
    manifest = json.loads((ROOT/'data/manifests/seoul-city-v1.json').read_text())
    raw = SOURCE/'seoul-polygons.geojson'
    if digest(raw) != manifest['extractHashes'][raw.name] or digest(SOURCE/'south-korea-261016.osm.pbf') != PBF_HASH:
        raise ValueError('보관된 공개 원본 무결성 오류')
    features = json.loads(raw.read_text())['features']
    city = shape(next(f['geometry'] for f in features if f['properties'].get('osm_id') == '2297418'))
    transform = pyproj.Transformer.from_crs(4326, 5186, always_xy=True, allow_ballpark=False)
    project = lambda g: shapely.transform(g, transform.transform, interleaved=False)
    districts, buildings, parkings = [], [], []
    for f in features:
        p = f['properties']
        kind = ('building' if p.get('building') not in (None, 'no') else
                'parking' if p.get('amenity') == 'parking' else
                'district' if p.get('boundary') == 'administrative' and p.get('admin_level') == '6' else None)
        if not kind:
            continue
        g = shape(f['geometry'])
        if g.is_empty or not g.is_valid or not city.covers(g.representative_point()):
            continue
        tags = p.get('other_tags') or {}
        if isinstance(tags, str):
            tags = json.loads(tags)
        native = project(g)
        if native.geom_type == 'MultiPolygon' and len(native.geoms) == 1:
            native = native.geoms[0]
        item = {'id': source_id(p), 'geometry': native, 'tags': tags}
        if kind == 'district':
            if g.intersection(city).area/g.area >= .99:
                districts.append({'id': p['osm_id'], 'name': p['name'], 'geometry': native})
        elif kind == 'building':
            item['heightM'], item['heightSource'] = height(tags)
            buildings.append(item)
        elif (tags.get('parking') == 'surface' or tags.get('surface') in HARD_SURFACES) and \
                tags.get('parking') not in {'underground', 'multi-storey', 'rooftop', 'carports', 'garage_boxes'} and \
                tags.get('surface') not in EXCLUDED_SURFACES:
            parkings.append(item)
    if len(districts) != 25:
        raise ValueError('서울 25개 구 경계 확인 실패')
    return sorted(districts, key=lambda d: d['name']), buildings, parkings, manifest


def select_block(district, buildings, tree, parkings):
    boundary = district['geometry']
    options = sorted((p for p in parkings if boundary.covers(p['geometry'])),
                     key=lambda p: (p['geometry'].distance(boundary.centroid), p['id']))
    for parking in options:
        ground = ground_cells(parking, buildings, tree)
        if len(ground) < 5:
            continue
        point = parking['geometry'].representative_point()
        nearby = [buildings[i] for i in tree.query(point.buffer(350), predicate='intersects')]
        roofs = []
        for b in sorted(nearby, key=lambda b: (b['geometry'].distance(point), b['id'])):
            g = b['geometry']
            if g.geom_type != 'Polygon' or len(g.interiors) or not 60 <= g.area <= 5000 or not boundary.covers(g):
                continue
            if any(g.intersection(r['geometry']).area > .001 for r in roofs):
                continue
            roofs.append(b)
            if len(roofs) == 8:
                return parking, ground, roofs
    raise ValueError(district['name']+'에서 확인된 8개 옥상·5개 지상 후보 부족')


def make_region(district, parking, ground, roofs, buildings, tree, source_hash):
    point = parking['geometry'].representative_point()
    origin = [round(point.x), round(point.y)]
    study = box(origin[0]-500, origin[1]-500, origin[0]+500, origin[1]+500)
    nearby = sorted((buildings[i] for i in tree.query(study, predicate='intersects')), key=lambda b: b['id'])
    features = []
    for b in nearby:
        g = b['geometry']; p = g.representative_point()
        features.append({'id': b['id'], 'kind': 'building', 'name': '',
                         'polygons': local_polygons(g, origin), 'heightM': b['heightM'],
                         'heightSource': 'OSM_TAG' if b['heightSource'] == 'OSM_HEIGHT_TAG' else b['heightSource'],
                         'displayAreaM2': g.area, 'center': [p.x-origin[0], p.y-origin[1]]})
    features.append({'id': parking['id'], 'kind': 'transport', 'transportType': 'parking',
                     'polygons': local_polygons(parking['geometry'], origin)})
    reverse = pyproj.Transformer.from_crs(5186, 4326, always_xy=True, allow_ballpark=False)
    center = list(reverse.transform(*origin))
    bounds = [*reverse.transform(*study.bounds[:2]), *reverse.transform(*study.bounds[2:])]
    map_id = 'seoul-osm-v1-'+district['id']
    title = district['name']+' · 공개 도형 실험구역'
    snapshot = {'id': map_id, 'title': title, 'subtitle': 'OSM 2026.10 · 구별 대표 블록',
                'origin': center, 'originProjected': origin, 'coordinateSystem': 'EPSG:5186_LOCAL_TRANSLATION',
                'bounds': bounds, 'widthM': 1000, 'depthM': 1000, 'validationLevel': 'DRAFT',
                'officialEvaluationAvailable': False, 'sourceHash': source_hash, 'features': features,
                'attribution': '© OpenStreetMap contributors · Geofabrik · ODbL 1.0',
                'licenseUrl': 'https://www.openstreetmap.org/copyright',
                'limitations': ['구 전체 유역이 아닌 공개 건물·지상 주차장의 선택 표면 비교',
                    '2026 공개 형상에서 2024 성동 관측 강우 공통 재생; 해당 지역 실측 강우 아님',
                    '실제 지표고·관망·토양 보정 없음; 높이는 표시용 태그 또는 추정',
                    '설치 적합성 UNKNOWN; 주차장 지상·포장 태그도 현장 조사 결과가 아님']}
    cells = []
    for kind, items in [('ROOF', roofs), ('GROUND', ground)]:
        for i, item in enumerate(items, 1):
            roof = kind == 'ROOF'
            g = item['geometry'] if roof else item
            p = g.representative_point()
            cell = {'id': ('R' if roof else 'G')+str(i), 'kind': kind,
                    'name': ('옥상 후보 ' if roof else '주차장 실험 구역 ')+str(i),
                    'coordinates': local_polygons(g, origin)[0][0],
                    'center': [p.x-origin[0], p.y-origin[1]], 'areaM2': g.area,
                    'maxAreaM2': math.floor(g.area*(.6 if roof else .8)*100)/100,
                    'heightM': item['heightM'] if roof else .12,
                    'allowedTypes': ['GREEN_ROOF'] if roof else ['RAIN_GARDEN', 'PERMEABLE_PAVEMENT'],
                    'areaEvidence': 'OSM_EPSG5186_FOOTPRINT' if roof else 'DESIGN_GRID_INSIDE_OSM_SURFACE_PARKING',
                    'siteEligibility': 'UNKNOWN', 'eligibilityEvidence': 'UNKNOWN_DESIGN_CAP_NOT_SITE_APPROVED',
                    'sourceIds': [item['id'] if roof else parking['id']]}
            if roof:
                cell['buildingId'] = item['id']
            cells.append(cell)
    return snapshot, cells


def main():
    districts, buildings, parkings, source = read_shapes()
    tree = STRtree([b['geometry'] for b in buildings])
    old_catalog = json.loads((ROOT/'data/models/catalog.json').read_text())
    catalog = {**old_catalog, 'models': [e for e in old_catalog['models'] if not e['id'].startswith('seoul-osm-v1-')]}
    maps = json.loads((ROOT/'frontend/public/data/maps.json').read_text())
    maps['maps'] = [m for m in maps['maps'] if not m['id'].startswith('seoul-osm-v1-')]
    regions = []
    generator_hash = digest(Path(__file__))
    geod = pyproj.Geod(ellps='WGS84')
    for district in districts:
        parking, ground, roofs = select_block(district, buildings, tree, parkings)
        snapshot, cells = make_region(district, parking, ground, roofs, buildings, tree, PBF_HASH)
        data = payload(snapshot); map_hash = sha(data); map_file = snapshot['id']+'.json'
        if len(data) > 2*1024*1024:
            raise ValueError('지도 크기 상한 초과')
        write(ROOT/'frontend/public/data'/map_file, data)
        entries = []
        for date in EVENTS:
            model = json.loads((ROOT/'data/models'/f'seongsu-421-{date}.json').read_text())
            identifier = snapshot['id']+'-421-'+date
            model.update({'id': identifier, 'title': district['name']+' · 공통 강우 '+date,
                          'mapId': snapshot['id'], 'mapTitle': district['name']+' 대표 블록',
                          'mapSnapshotHash': map_hash, 'geometrySourceHash': PBF_HASH,
                          'geometryModelGeneratorSha256': generator_hash,
                          'geometryEvidence': 'OSM_20261016_PROJECTED_FOOTPRINT_AND_SURFACE_PARKING_GRID',
                          'geometryPolicy': {'roofAreaCapFraction': .6, 'groundAreaCapFraction': .8,
                                             'evidence': 'ASSUMED_DESIGN_LIMIT_NOT_SURVEYED'},
                          'cells': copy.deepcopy(cells), 'maxPlacements': len(cells),
                          'regionalRainfallUse': 'COMMON_OBSERVED_REPLAY_NOT_LOCAL_OBSERVATION',
                          'district': {'id': district['id'], 'name': district['name']},
                          'parkingEvidence': {'sourceId': parking['id'],
                              'parking': parking['tags'].get('parking'), 'surface': parking['tags'].get('surface')}})
            rain = model['rainfall']; station = rain['stationMetadata']
            rain['stationDistanceKm'] = round(geod.inv(station['longitude'], station['latitude'], *snapshot['origin'])[2]/1000, 3)
            rain['stationDistanceEvidence'] = '기상청 현재 공개 좌표에서 해당 대표 블록 중심까지 거리; 과거 위치·지역 강우 대표성 미검증'
            model['assumptions'] = [a.replace('성수동 전체', '해당 구 전체') for a in model['assumptions']]
            model['assumptions'] += snapshot['limitations'] + ['옥상 60%·지상 격자 80% 상한은 설계 가정이며 실제 시공 가능 면적이 아님']
            raw = payload(model)
            entry = {'id': identifier, 'file': identifier+'.json', 'sha256': sha(raw)}
            for folder in ('data/models', 'backend/src/main/resources/models'):
                write(ROOT/folder/entry['file'], raw)
            entries.append(entry)
        catalog['models'] += entries
        maps['maps'].append({'id': snapshot['id'], 'file': map_file, 'sha256': map_hash,
                             'modelHashes': [e['sha256'] for e in entries]})
        regions.append({'districtId': district['id'], 'districtName': district['name'],
                        'mapId': snapshot['id'], 'mapFile': map_file, 'mapSha256': map_hash,
                        'center': [v-o for v,o in zip(snapshot['originProjected'], ORIGIN)],
                        'defaultModelHash': entries[-1]['sha256'], 'modelHashes': [e['sha256'] for e in entries],
                        'roofCount': len(roofs), 'groundCount': len(ground), 'parkingSourceId': parking['id']})
        print(district['name'], len(snapshot['features']), '표시 도형, 관측 강우 3개 연결', flush=True)
    for folder in ('data/models', 'backend/src/main/resources/models'):
        write(ROOT/folder/'catalog.json', payload(catalog), mutable=True)
    write(ROOT/'frontend/public/data/maps.json', payload(maps), mutable=True)
    registry = {'schemaVersion': 1, 'sourceSha256': PBF_HASH, 'sourceUrl': SOURCE_URL,
                'generatorSha256': generator_hash, 'regions': regions,
                'rainfallUse': 'COMMON_OBSERVED_REPLAY_NOT_LOCAL_OBSERVATION',
                'extractSha256': source['extractHashes']['seoul-polygons.geojson']}
    raw = payload(registry)
    write(ROOT/'frontend/public/data/seoul-play-v1.json', raw)
    write(ROOT/'data/manifests/seoul-play-v1.json', raw)
    print('구별 플레이 목록 SHA256', sha(raw), flush=True)


if __name__ == '__main__':
    main()
