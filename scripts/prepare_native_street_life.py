"""원형 지도에 빠진 교통 표시를 별도 묶음으로 생성하며 계산 후보는 변경하지 않는다."""
import argparse
from collections import Counter
from contextlib import closing
import gzip
import json
import math
from pathlib import Path
import sqlite3

import shapely
from shapely.affinity import translate
from shapely.geometry import LineString, Point, box, mapping, shape

import prepare_seoul_topography as source
import prepare_seoul_spatial as spatial
import topography_catalog as native
from prepare_topography_objects import DistrictAssignment, object_key
from prepare_topography_scene import ORIGIN

BASE = source.ROOT / 'data/private/vworld-seoul-topography-20260307'
CITY = source.ROOT / 'frontend/public/data/seoul-native-v1/city.json'
OUTPUT = source.ROOT / 'frontend/public/data/seoul-street-life-v1'


def components(geometry, kind):
    if geometry.is_empty:
        return []
    if geometry.geom_type == kind:
        return [geometry]
    return [part for child in getattr(geometry, 'geoms', []) for part in components(child, kind)]


def axis(geometry):
    points = list(geometry.minimum_rotated_rectangle.exterior.coords)
    a, b = max(zip(points, points[1:]), key=lambda pair: Point(pair[0]).distance(Point(pair[1])))
    length = math.dist(a, b)
    return (b[0] - a[0]) / length, (b[1] - a[1]) / length


def walk_paths(geometry):
    paths = []
    # 원 보도 안쪽의 표시 선만 사용하며 구멍·분리된 면 사이를 연결하지 않는다.
    for polygon in components(geometry.buffer(-0.4), 'Polygon'):
        dx, dy = axis(polygon)
        p = polygon.representative_point()
        size = math.hypot(polygon.bounds[2] - polygon.bounds[0], polygon.bounds[3] - polygon.bounds[1]) + 1
        line = LineString([(p.x - dx * size, p.y - dy * size), (p.x + dx * size, p.y + dy * size)])
        paths.extend(part for part in components(line.intersection(polygon), 'LineString') if part.length >= 5)
    return sorted(paths, key=lambda line: shapely.to_wkb(shapely.normalize(line)))


def stripes(geometry):
    result = []
    for polygon in components(geometry, 'Polygon'):
        dx, dy = axis(polygon)
        p = polygon.representative_point()
        size = math.hypot(polygon.bounds[2] - polygon.bounds[0], polygon.bounds[3] - polygon.bounds[1]) + 1
        for i in range(-math.ceil(size / 1.2), math.ceil(size / 1.2) + 1):
            x, y = p.x + dx * i * 1.2, p.y + dy * i * 1.2
            line = LineString([(x - dy * size, y + dx * size), (x + dy * size, y - dx * size)])
            result.extend(components(line.buffer(0.25, cap_style='flat').intersection(polygon), 'Polygon'))
    return result


def parked_cars(geometry, obstacles, identifier):
    usable = geometry.difference(shapely.union_all(obstacles)) if obstacles else geometry
    result = []
    # 차량 크기·간격·점유는 게임 표시 가정이며 주차 칸이나 실제 수용량으로 제공하지 않는다.
    for polygon in components(usable, 'Polygon'):
        minx, miny, maxx, maxy = polygon.bounds
        for y in range(math.ceil(miny / 6), math.floor(maxy / 6) + 1):
            for x in range(math.ceil(minx / 3.2), math.floor(maxx / 3.2) + 1):
                px, py = x * 3.2, y * 6
                car = box(px - 1.05, py - 2.35, px + 1.05, py + 2.35)
                if polygon.covers(car):
                    seed = int(source.digest(f'{identifier}:{x}:{y}'.encode())[:8], 16) / 2**32
                    result.append(dict(center=[px - ORIGIN[0], py - ORIGIN[1]], angle=0,
                        corners=[[a - ORIGIN[0], b - ORIGIN[1]] for a, b in car.exterior.coords], seed=seed))
                    if len(result) >= 120:
                        return result
    return result


def polygons(geometry):
    body = mapping(geometry)
    return [body['coordinates']] if body['type'] == 'Polygon' else body['coordinates']


def build(output):
    if output.exists() or output.is_symlink():
        raise ValueError('기존 표시 묶음 덮어쓰기 금지')
    city_sha, scene_sha = spatial.file_sha256(CITY), spatial.file_sha256(BASE / 'scene-v1/catalog.json')
    city, scene = native.read_json(CITY, 16 * 1024**2), native.read_json(BASE / 'scene-v1/catalog.json', 16 * 1024**2)
    summary = native.read_json(BASE / 'spatial-v1/summary.json')
    catalog = native.SpatialCatalog(BASE / 'spatial-v1', summary)
    assignment = DistrictAssignment(native.read_json(source.ROOT / 'data/derived/seoul-district-boundaries-v1.json', 4 * 1024**2))
    tiles = {tile['id']: dict(schemaVersion=1, id=tile['id'], crosswalks=[], parkingLots=[], walkPaths=[]) for tile in city['tiles']}
    counts, links = Counter(), {}
    generator_sha = spatial.file_sha256(__file__)
    for index, entry in enumerate(scene['tiles']):
        with source.source_stream(BASE / 'scene-v1' / entry['file'], entry['bytes'], entry['sha256'], 16 * 1024**2) as (stream, _):
            tile = json.load(stream)
        for feature in tile['features']:
            if feature['role'] != 'SIDEWALK_AREA':
                continue
            for number, line in enumerate(walk_paths(shape(feature['geometry']))):
                tiles[entry['id']]['walkPaths'].append(dict(id=feature['id'] + ':walk:' + str(number),
                    sourceObjectId=feature['id'], districtId=feature['districtId'], coordinates=list(line.coords)))
                counts['walkPaths'] += 1
        if (index + 1) % 100 == 0:
            print(source.canonical(dict(sidewalkTiles=index + 1, total=len(scene['tiles']))), flush=True)
    with closing(sqlite3.connect('file:' + str(catalog.database) + '?mode=ro&immutable=1', uri=True)) as db:
        db.execute('PRAGMA trusted_schema=OFF;')
        rows = db.execute("""SELECT f.fid,f.tile,f.layer,f.record_number,t.sha256,f.geometry_wkb,f.raw_shape_sha256,f.raw_dbf_sha256
            FROM features f JOIN tiles t ON t.tile=f.tile WHERE f.layer IN ('N1A_A0043325','N1A_C0430000')
            AND f.geometry_status='VALID' AND f.deleted=0 ORDER BY f.tile,f.layer,f.record_number""")
        seen = set()
        for fid, tile_id, layer, number, tile_sha, raw, shape_sha, dbf_sha in rows:
            geometry = shapely.from_wkb(raw)
            identifier = object_key(layer, geometry)
            links.setdefault(identifier, []).append(dict(fid=fid, sourceRecordId=source.record_id(tile_id, layer, number, tile_sha),
                rawShapeSha256=shape_sha, rawDbfSha256=dbf_sha))
            if identifier in seen:
                continue
            seen.add(identifier)
            district, _ = assignment.assign(geometry)
            if district is None:
                continue
            point = geometry.representative_point()
            key = f'{math.floor((point.x - ORIGIN[0]) / 1000)}_{math.floor((point.y - ORIGIN[1]) / 1000)}'
            if key not in tiles:
                raise ValueError('기본 지도에 없는 교통 타일')
            relative = translate(geometry, -ORIGIN[0], -ORIGIN[1])
            if layer == 'N1A_A0043325':
                tiles[key]['crosswalks'].append(dict(id=identifier, districtId=district, polygons=polygons(relative),
                    stripes=[polygons(part)[0] for part in stripes(relative)]))
                for number, line in enumerate(walk_paths(relative)):
                    tiles[key]['walkPaths'].append(dict(id=identifier + ':walk:' + str(number),
                        sourceObjectId=identifier, districtId=district, coordinates=list(line.coords)))
                    counts['walkPaths'] += 1
                counts['crosswalks'] += 1
            else:
                obstacles = [row['geometry'] for row in catalog.query(geometry.bounds,
                    ['N1A_B0010000', 'N1A_A0070000', 'N1A_A0110020', 'N1A_A0160024', 'N1A_E0032111', 'N1A_E0052114'])]
                slots = parked_cars(geometry, obstacles, identifier)
                tiles[key]['parkingLots'].append(dict(id=identifier, districtId=district, polygons=polygons(relative),
                    surfacePolygons=polygons(relative), bounds=list(relative.bounds), supports=[], slots=slots, displayOnly=True))
                counts['parkingLots'] += 1
                counts['parkedCarPositions'] += len(slots)
    output.mkdir()
    (output / 'tiles').mkdir()
    entries = []
    for key, tile in sorted(tiles.items()):
        for field in ('walkPaths', 'crosswalks', 'parkingLots'):
            tile[field].sort(key=lambda value: value['id'])
        raw = (source.canonical(tile) + '\n').encode()
        if len(raw) > 4 * 1024**2:
            raise ValueError('교통 표시 타일 용량 초과')
        stored = gzip.compress(raw, compresslevel=9, mtime=0)
        name = 'tiles/' + key + '.json.gz'
        (output / name).write_bytes(stored)
        entries.append(dict(id=key, file=name, sha256=source.digest(raw), bytes=len(raw), storedSha256=source.digest(stored), storedBytes=len(stored)))
    index = dict(schemaVersion=1, sourceCitySha256=city_sha, sourceSceneSha256=scene_sha,
        sourceSpatialSha256=summary['spatialSha256'], sourceObjectsSha256=city['sourceObjectsSha256'],
        originProjected=ORIGIN, tiles=entries, counts=dict(counts), generatorSha256=generator_sha,
        policy=dict(sourceGeometryPreserved=True, routesAreObserved=False, parkingStallsProvided=False,
            parkedCarsAreObserved=False, hydraulicInputsChanged=False, bridgeHeightIsSurveyed=False,
            pedestrianClearanceM=0.4, bridgeDisplayLiftM=6.5))
    (output / 'index.json').write_text(source.canonical(index) + '\n')
    if generator_sha != spatial.file_sha256(__file__) or city_sha != spatial.file_sha256(CITY):
        raise ValueError('생성 중 입력·코드 변경')
    evidence = dict(indexSha256=spatial.file_sha256(output / 'index.json'), **index,
        sourceLinks=links, versions=dict(shapely=shapely.__version__, geos=shapely.geos_version_string))
    (BASE / 'street-life-v1-evidence.json').write_text(source.canonical(evidence) + '\n')
    print(source.canonical(dict(indexSha256=evidence['indexSha256'], counts=dict(counts))), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    build(args.output.absolute())
