"""서울시 공개 침수흔적의 날짜 선별·표시 합집합·고정 타일 생성."""
import collections
from datetime import date
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import zipfile

from pyproj import CRS, Transformer
import shapely
from shapely.geometry import shape, box, Polygon

from prepare_public_infrastructure import raw_source

ROOT = Path(__file__).resolve().parents[1]
VERSION = 'seoul-flood-traces-20261018-v1'
ORIGIN = [198128., 551989.]
EVENTS = [
    ('seoul-20100921', 2010, '2010년 9월 집중호우', '2010-09-21', '2010-09-23'),
    ('seoul-20110727', 2011, '2011년 7월 집중호우', '2011-07-26', '2011-07-29'),
    ('seoul-20220808', 2022, '2022년 8월 집중호우', '2022-08-08', '2022-08-17'),
]


def payload(value):
    return (json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False) + '\n').encode()


def digest(value):
    return hashlib.sha256(value).hexdigest()


def source_date(value):
    text = str(value or '').strip()
    match = re.fullmatch(r'(\d{4})-?(\d{2})-?(\d{2})(?:\s*-\s*\d{4})?', text)
    if not match:
        return None
    try:
        return date(*(int(v) for v in match.groups()))
    except ValueError:
        return None


def membership(properties, start, end):
    observed = source_date(properties.get('F_SAT_YMD'))
    if observed is None:
        return 'START_DATE_UNKNOWN'
    return 'MATCHED' if date.fromisoformat(start) <= observed <= date.fromisoformat(end) else 'OTHER_EVENT'


def polygons(geometry):
    if geometry.geom_type == 'Polygon':
        return [geometry]
    return [p for g in getattr(geometry, 'geoms', []) for p in polygons(g)]


def geometry_payload(geometry):
    rings, vertices = [], []
    for polygon in polygons(geometry):
        for ring in [polygon.exterior, *polygon.interiors]:
            coordinates = [(round(x, 3), round(-y, 3)) for x, y in ring.coords]
            rings.append(' '.join(f'{"M" if i == 0 else "L"}{x},{y}'
                                  for i, (x, y) in enumerate(coordinates)) + ' Z')
    triangles = shapely.constrained_delaunay_triangles(geometry)
    area = 0.
    for triangle in triangles.geoms:
        area += triangle.area
        for x, y in list(triangle.exterior.coords)[:3]:
            vertices.extend((round(x, 3), round(y, 3)))
    if not math.isclose(area, geometry.area, abs_tol=1e-5, rel_tol=1e-8):
        raise ValueError('침수흔적 삼각분할 면적 불일치')
    return {'path': ' '.join(rings), 'triangleVertices': vertices}


def immutable_write(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() != raw:
        raise ValueError('기존 침수흔적 버전 변경: 새 버전 필요')
    path.write_bytes(raw)


def read_source(year):
    manifest_path = ROOT / f'data/manifests/seoul-flood-traces-{year}-20261018.json'
    manifest = json.loads(manifest_path.read_bytes())
    path, _ = raw_source(manifest, False)
    destination = ROOT / f'data/private/flood-traces-20261018/{year}'
    destination.mkdir(parents=True, exist_ok=True)
    extensions = set()
    with zipfile.ZipFile(path) as archive:
        if len(archive.infolist()) > 20 or sum(v.file_size for v in archive.infolist()) > 150_000_000:
            raise ValueError('침수흔적 원본 크기 초과')
        for member in archive.infolist():
            suffix = Path(member.filename).suffix.lower()
            if suffix not in ('.shp', '.shx', '.dbf', '.prj', '.cpg'):
                continue
            if suffix in extensions:
                raise ValueError('침수흔적 복수 레이어')
            extensions.add(suffix)
            (destination / f'traces{suffix}').write_bytes(archive.read(member))
    if not {'.shp', '.shx', '.dbf', '.prj'} <= extensions:
        raise ValueError('침수흔적 원본 구성 누락')
    if CRS.from_wkt((destination / 'traces.prj').read_text()).to_epsg() != 5179:
        raise ValueError('침수흔적 좌표계 불일치')
    result = subprocess.run(['ogr2ogr', '--config', 'SHAPE_ENCODING', 'CP949', '-f', 'GeoJSON',
        '/vsistdout/', str(destination / 'traces.shp')], capture_output=True, check=True, timeout=60)
    return manifest_path, manifest, json.loads(result.stdout)['features']


def main():
    destination = ROOT / 'backend/src/main/resources/floodtrace' / VERSION
    transformer = Transformer.from_crs(5179, 5186, always_xy=True)
    def local(x, y, z=None):
        x, y = transformer.transform(x, y)
        return x - ORIGIN[0], y - ORIGIN[1]
    events, lineage = [], []
    for event_id, year, title, start, end in EVENTS:
        source_path, source, features = read_source(year)
        counts = collections.Counter()
        selected, source_indices = [], []
        for i, feature in enumerate(features):
            status = membership(feature['properties'], start, end)
            if status != 'MATCHED':
                counts[status] += 1
                continue
            geometry = shape(feature['geometry'])
            if not geometry.is_valid or geometry.is_empty or geometry.geom_type not in ('Polygon', 'MultiPolygon'):
                counts['INVALID_GEOMETRY'] += 1
                continue
            local_geometry = shapely.transform(geometry, local, interleaved=False)
            if not all(math.isfinite(v) and abs(v) < 60000 for v in local_geometry.bounds):
                counts['OUTSIDE_DISPLAY_RANGE'] += 1
                continue
            counts['INCLUDED'] += 1
            if source_date(feature['properties'].get('F_END_YMD')) is None:
                counts['INCLUDED_WITHOUT_END_DATE'] += 1
            selected.append(local_geometry)
            source_indices.append(i)
        union = shapely.union_all(selected)
        tiles = []
        minx, miny, maxx, maxy = union.bounds
        tiled_area = 0.
        for col in range(math.floor(minx / 4000), math.floor(maxx / 4000) + 1):
            for row in range(math.floor(miny / 4000), math.floor(maxy / 4000) + 1):
                bounds = [col * 4000, row * 4000, (col + 1) * 4000, (row + 1) * 4000]
                clipped = union.intersection(box(*bounds))
                if clipped.area <= 0:
                    continue
                tile_id = f'{col}_{row}'
                content = dict(eventId=event_id, id=tile_id, **geometry_payload(clipped))
                raw = payload(content)
                immutable_write(destination / event_id / f'{tile_id}.json', raw)
                tiles.append(dict(id=tile_id, bounds=bounds, sha256=digest(raw), bytes=len(raw)))
                tiled_area += clipped.area
        if not math.isclose(tiled_area, union.area, abs_tol=1e-4, rel_tol=1e-8):
            raise ValueError('침수흔적 타일 면적 불일치')
        event = dict(id=event_id, title=title, year=year, periodStart=start, periodEnd=end,
            sourceSha256=source['sha256'], fileModifiedAt=source['fileModifiedAt'],
            recordCount=len(features), includedCount=counts['INCLUDED'], statusCounts=dict(counts),
            unionAreaM2=round(union.area, 3), tiles=tiles)
        events.append(event)
        lineage.append({'manifest': str(source_path.relative_to(ROOT)), 'sha256': digest(source_path.read_bytes()),
                        'includedRecordIndexSha256': digest(payload(source_indices)),
                        'event': event_id, 'statusCounts': dict(counts)})
        print(event_id, dict(counts), len(tiles), sum(t['bytes'] for t in tiles), flush=True)
    catalog = {'version': VERSION, 'usage': 'OBSERVED_EVENT_EXTENT_REFERENCE', 'projection': 'EPSG:5186',
               'originM': ORIGIN, 'displayRoundingM': .001, 'tileSizeM': 4000,
               'sourceUrl': 'https://data.seoul.go.kr/dataList/OA-15636/F/1/datasetView.do',
               'publisher': '서울특별시', 'license': 'KOGL_TYPE_1', 'events': events}
    raw = payload(catalog)
    immutable_write(destination / 'catalog.json', raw)
    manifest = {'version': VERSION, 'catalogSha256': digest(raw), 'sources': lineage,
        'generatorSha256': digest(Path(__file__).read_bytes()), 'shapely': shapely.__version__,
        'geos': shapely.geos_version_string,
        'sourceCrs': 'EPSG:5179', 'displayCrs': 'EPSG:5186',
        'limitations': ['사건 전체 기록이며 재생 분 시각의 수심·모의 결과 아님',
            '원본 미등록 지역은 비침수 판정 불가', '유효하지 않은 도형은 원본 보존 후 표시 제외',
            '현재 공개 수정본이며 사건 당시 공개된 자료 버전 아님',
            '주소·원본 로컬 경로 미노출; 침수심 수치·수직 형상 미사용']}
    immutable_write(ROOT / f'data/manifests/{VERSION}.json', payload(manifest))
    print('catalog sha256', digest(raw))


if __name__ == '__main__':
    main()
