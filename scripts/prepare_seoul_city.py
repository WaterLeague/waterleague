"""보관된 OSM 대한민국 원본의 서울 전역 표시 타일 생성."""
import hashlib
import json
import math
import subprocess
from collections import Counter, defaultdict
from pathlib import Path

import pyproj
import shapely
from shapely.geometry import Polygon, MultiPolygon, Point, box, shape

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT/'data/private/seoul-city-20261017'
OUTPUT = ROOT/'frontend/public/data/seoul-v1'
PBF_HASH = '5844138cdd171124886805c0c943bdab9bc009b8102478e9b6e720bafa82f87f'
SOURCE_URL = 'https://download.geofabrik.de/asia/south-korea-261016.osm.pbf'
ORIGIN = [198128.0, 551989.0]
TILE_SIZE = 1000


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write(path, value):
    payload = (json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)+'\n').encode()
    if path.exists() and path.read_bytes() != payload:
        raise ValueError('다른 버전의 도시 자료 덮어쓰기 거부')
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
    return {'sha256': hashlib.sha256(payload).hexdigest(), 'bytes': len(payload)}


def polygons(geometry, tolerance=0):
    if tolerance:
        geometry = geometry.simplify(tolerance, preserve_topology=True)
    parts = [geometry] if geometry.geom_type == 'Polygon' else list(geometry.geoms)
    return [[[[round(x-ORIGIN[0], 2), round(y-ORIGIN[1], 2)] for x, y in ring.coords]
             for ring in [polygon.exterior, *polygon.interiors]] for polygon in parts
            if polygon.geom_type == 'Polygon' and polygon.area > 0]


def height(tags):
    for key, factor, evidence in (('height', 1, 'OSM_HEIGHT_TAG'),
                                  ('building:levels', 3.2, 'LEVELS_ESTIMATE')):
        raw = tags.get(key)
        if raw is None:
            continue
        try:
            # 수치 뒤 m만 허용하며 피트·범위·복합 문자열을 임의 해석하지 않음.
            value = float(raw.removesuffix(' m').strip())*factor
            if math.isfinite(value) and 0 < value <= 650:
                return round(value, 2), evidence
        except (ValueError, TypeError, AttributeError):
            pass
    return 9.6, 'VISUAL_ASSUMPTION'


def main():
    pbf = SOURCE/'south-korea-261016.osm.pbf'
    if digest(pbf) != PBF_HASH:
        raise ValueError('대한민국 원본 무결성 오류')
    paths = [SOURCE/'seoul-polygons.geojson', SOURCE/'seoul-lines.geojson']
    features = json.loads(paths[0].read_text())['features']
    cities = [f for f in features if f['properties'].get('osm_id') == '2297418'
              and f['properties'].get('name') == '서울특별시'
              and f['properties'].get('boundary') == 'administrative']
    if len(cities) != 1:
        raise ValueError('서울 원본 행정경계 확인 실패')
    geographic_city = shape(cities[0]['geometry'])
    if not geographic_city.is_valid:
        raise ValueError('서울 행정경계 유효성 오류')
    transformer = pyproj.Transformer.from_crs(4326, 5186, always_xy=True, allow_ballpark=False)
    project = lambda g: shapely.transform(g, transformer.transform, interleaved=False)
    city = project(geographic_city)
    districts, surfaces, buildings, skipped = [], [], [], Counter()
    seen = set()
    for feature in features:
        p = feature['properties']
        kind = ('building' if p.get('building') not in (None, 'no') else
                'district' if p.get('boundary') == 'administrative' and p.get('admin_level') == '6' else
                'water' if p.get('natural') == 'water' or p.get('landuse') == 'reservoir' else
                'green' if p.get('natural') in ('wood', 'scrub', 'grassland') or p.get('landuse') in
                ('forest', 'grass', 'recreation_ground') or p.get('leisure') in ('park', 'garden') else None)
        if not kind:
            continue
        g = shape(feature['geometry'])
        if not g.is_valid or g.is_empty or g.geom_type not in ('Polygon', 'MultiPolygon'):
            skipped[kind+'_invalid_geometry'] += 1
            continue
        if not g.intersects(geographic_city):
            continue
        native = project(g)
        if kind == 'district':
            # 인접 시·군은 서울 내부 면적 비율로 제외.
            if native.intersection(city).area/native.area < .99:
                continue
            point = native.representative_point()
            districts.append({'id': p['osm_id'], 'name': p['name'], 'polygons': polygons(native, 5),
                              'center': [point.x-ORIGIN[0], point.y-ORIGIN[1]],
                              'areaKm2': round(native.area/1e6, 2)})
            continue
        if kind == 'building':
            if not geographic_city.covers(g.representative_point()):
                continue
            identifier = 'relation/'+p['osm_id'] if p.get('osm_id') else 'way/'+p['osm_way_id']
            if identifier in seen:
                raise ValueError('서울 건물 식별자 중복')
            seen.add(identifier)
            tags = p.get('other_tags') or {}
            if isinstance(tags, str):
                tags = json.loads(tags)
            value, evidence = height(tags)
            point = native.representative_point()
            buildings.append({'id': identifier, 'polygons': polygons(native), 'heightM': value,
                              'heightSource': evidence, 'areaM2': round(native.area, 2),
                              'center': [round(point.x-ORIGIN[0], 2), round(point.y-ORIGIN[1], 2)]})
            continue
        clip = native.intersection(city)
        if clip.area < (10000 if kind == 'water' else 20000):
            continue
        polys = polygons(clip, 8)
        if polys:
            surfaces.append({'kind': kind, 'polygons': polys})
    if len(districts) != 25 or not buildings:
        raise ValueError(f'서울 구역·건물 수 오류: {len(districts)}, {len(buildings)}')
    features = None
    roads = []
    for feature in json.loads(paths[1].read_text())['features']:
        p = feature['properties']
        if p.get('highway') not in ('motorway', 'trunk', 'primary', 'secondary', 'tertiary'):
            continue
        g = shape(feature['geometry'])
        if not g.is_valid or g.is_empty or not g.intersects(geographic_city):
            continue
        g = project(g).intersection(city).simplify(6, preserve_topology=True)
        lines = [g] if g.geom_type == 'LineString' else getattr(g, 'geoms', [])
        for line in lines:
            if line.geom_type == 'LineString' and line.length > 40:
                roads.append({'class': p['highway'], 'coordinates': [[round(x-ORIGIN[0], 2),
                              round(y-ORIGIN[1], 2)] for x, y in line.coords]})
    buckets = defaultdict(list)
    for b in sorted(buildings, key=lambda b: b['id']):
        x, y = b['center']
        buckets[(math.floor(x/TILE_SIZE), math.floor(y/TILE_SIZE))].append(b)
    tiles = []
    for (x, y), items in sorted(buckets.items()):
        name = f'{x}_{y}.json'
        metadata = write(OUTPUT/'tiles'/name, {'schemaVersion': 1, 'id': f'{x}_{y}', 'buildings': items})
        tiles.append({'id': f'{x}_{y}', 'file': 'tiles/'+name, 'bounds': [x*TILE_SIZE, y*TILE_SIZE,
                     (x+1)*TILE_SIZE, (y+1)*TILE_SIZE], 'buildingCount': len(items), **metadata})
    overview = sorted(buildings, key=lambda b: (-b['heightM']*math.sqrt(b['areaM2']), b['id']))[:1200]
    minx, miny, maxx, maxy = city.bounds
    snapshot = {'schemaVersion': 1, 'id': 'seoul-osm-20261016', 'sourceSha256': PBF_HASH,
                'sourceUrl': SOURCE_URL, 'attribution': '© OpenStreetMap contributors · Geofabrik',
                'licenseUrl': 'https://www.openstreetmap.org/copyright', 'sourceDate': '2026-10-16',
                'coordinateSystem': 'EPSG:5186', 'originProjected': ORIGIN, 'tileSizeM': TILE_SIZE,
                'bounds': [minx-ORIGIN[0], miny-ORIGIN[1], maxx-ORIGIN[0], maxy-ORIGIN[1]],
                'boundary': polygons(city, 5), 'districts': sorted(districts, key=lambda d: d['name']),
                'surfaces': surfaces, 'roads': roads, 'overviewBuildings': overview,
                'buildingCount': len(buildings), 'heightEvidenceCounts': dict(Counter(b['heightSource'] for b in buildings)),
                'tiles': tiles, 'skipped': dict(skipped),
                'playAreas': [{'id': 'seongsu-ngii-2025-v2', 'name': '성수 · 연무장길',
                    'center': [v-o for v,o in zip(transformer.transform(127.054,37.54425),ORIGIN)],
                    'status': 'EXPLORATORY'}],
                'limitations': ['서울 행정경계 내 공개 OSM 형상이며 건물 누락·변경 가능',
                    '높이는 원본 태그·층수×3.2m·태그 미확인 시 9.6m 표현용 가정',
                    '평탄한 지면; 실제 지표고·관망·침수 깊이 미반영',
                    '전역 탐색 지도이며 지역별 수문 계산 모델 연결은 별도',
                    'OSM 관계 도형의 GDAL 조립 후 유효 도형만 표시; 원본 누락·조립 경고의 완전성 미검증']}
    metadata = write(OUTPUT/'city.json', snapshot)
    manifest = {'schemaVersion': 1, 'sourceUrl': SOURCE_URL, 'sourceSha256': PBF_HASH,
                'sourceBytes': pbf.stat().st_size, 'sourceDirectory': 'data/private/seoul-city-20261017',
                'importedLayers': ['multipolygons', 'lines'], 'gdalVersion': subprocess.check_output(
                    ['ogrinfo','--version'], text=True).strip(), 'pyproj': pyproj.__version__,
                'shapely': shapely.__version__, 'generatorSha256': digest(Path(__file__)),
                'extractHashes': {p.name: digest(p) for p in paths}, 'city': metadata,
                'buildingCount': len(buildings), 'districtCount': len(districts), 'tileCount': len(tiles),
                'derivedBytes': metadata['bytes']+sum(t['bytes'] for t in tiles),
                'skipped': dict(skipped), 'license': 'ODbL-1.0', 'licenseUrl': snapshot['licenseUrl'],
                'transform': 'EPSG:4326 to EPSG:5186; local translation; 0.01m display rounding',
                'modelInput': False, 'limitations': snapshot['limitations']}
    write(ROOT/'data/manifests/seoul-city-v1.json', manifest)
    print(json.dumps({k: manifest[k] for k in ('buildingCount','districtCount','tileCount','derivedBytes','city','skipped')},ensure_ascii=False))


if __name__ == '__main__':
    main()
