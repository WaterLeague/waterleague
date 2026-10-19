"""같은 공간 객체에서 원형을 절단하지 않는 시야별 지도 파일 생성."""
import argparse
from collections import Counter
from contextlib import closing
import json
import math
import os
from pathlib import Path
import shutil
import sqlite3
from urllib.parse import quote

import shapely
from shapely.affinity import translate
from shapely.geometry import mapping, shape

import prepare_seoul_topography as source
import prepare_seoul_spatial as spatial
import topography_catalog as native

ORIGIN = (198128., 551989.)
TILE_SIZE = 1000
OBJECT_DIRECTORY = source.ROOT / 'data/private/vworld-seoul-topography-20260307/objects-v1'
BOUNDARIES = source.ROOT / 'data/derived/seoul-district-boundaries-v1.json'
OUTPUT = source.ROOT / 'data/private/vworld-seoul-topography-20260307/scene-v1'


def display_record(identifier, role, raw, area, length, district, attribute_status, overlaps, properties):
    geometry = shapely.from_wkb(raw)
    projected_center = geometry.representative_point()
    body = {'id': identifier, 'role': role, 'districtId': district,
        'geometry': mapping(translate(geometry, -ORIGIN[0], -ORIGIN[1])),
        'center': [projected_center.x - ORIGIN[0], projected_center.y - ORIGIN[1]],
        'sourceAreaM2': area, 'sourceLengthM': length,
        'geometryEligibility': 'ATTRIBUTE_CONFLICT' if attribute_status != 'CONSISTENT' else
            'UNRESOLVED_OVERLAP' if overlaps else 'GEOMETRY_ONLY',
        'constructionEligibility': 'UNKNOWN'}
    if role == 'BUILDING_FOOTPRINT':
        floors, state = native.numeric_value(properties.get('층수'))
        known = attribute_status == 'CONSISTENT' and state == 'VALUE' and 0 < floors <= 200 and floors == int(floors)
        # 층수 환산은 표시 가정이며 미확인 높이는 낮은 평면 표시로 구분한다.
        body['heightM'] = float(floors) * 3.2 if known else .3
        body['heightBasis'] = 'FLOOR_COUNT_DISPLAY_ASSUMPTION' if known else 'UNKNOWN_HEIGHT_FLAT_DISPLAY'
        body['aboveGroundFloors'] = int(floors) if known else None
        body['buildingKind'] = properties.get('종류') if attribute_status == 'CONSISTENT' else None
    elif role == 'ROAD_CENTERLINE':
        body['roadClass'] = properties.get('도로구분')
        body['oneWayObservation'] = properties.get('일방통행')
        body['trafficDirection'] = 'BIDIRECTIONAL' if properties.get('일방통행') == '양방통행' else 'UNKNOWN'
        body['reportedWidthRaw'] = properties.get('도로폭')
        body['reportedWidthUnit'] = 'NOT_CONFIRMED'
    return body, geometry.bounds


def write_json(path, value):
    raw = (source.canonical(value) + '\n').encode()
    with path.open('xb') as stream:
        stream.write(raw)
    return {'sha256': source.digest(raw), 'bytes': len(raw)}


def build(directory, boundaries, output, progress=None):
    summary = native.read_json(directory / 'summary.json')
    code_paths = {'generatorSha256': Path(__file__), 'decoderSha256': Path(native.__file__),
                  'spatialReaderSha256': Path(spatial.__file__), 'sourceReaderSha256': Path(source.__file__)}
    code_hashes = {key: spatial.file_sha256(path) for key, path in code_paths.items()}
    if summary['decoderSha256'] != code_hashes['decoderSha256']:
        raise source.TopographyDataError('객체와 지도 해독 코드 불일치')
    if os.path.lexists(output) or output.parent.resolve() != output.parent.absolute():
        raise source.TopographyDataError('기존 지도 출력·출력 링크 덮어쓰기 금지')
    with source.source_stream(directory / 'objects.sqlite', expected_sha256=summary['objectsSha256'], limit=16 * 1024**3):
        pass
    if source.digest(source.canonical(boundaries).encode()) != summary['boundaryContentSha256']:
        raise source.TopographyDataError('객체와 지도 자치구 경계 불일치')
    output.mkdir(mode=0o700)
    counts, entries = Counter(), []
    try:
        (output / 'tiles').mkdir()
        with closing(sqlite3.connect(output / 'staging.sqlite')) as staging:
            staging.executescript('''PRAGMA cache_size=-65536;
                CREATE TABLE records(tile TEXT,id TEXT,payload TEXT,minx REAL,miny REAL,maxx REAL,maxy REAL);
                CREATE INDEX tile_records ON records(tile,id);''')
            with closing(sqlite3.connect('file:' + quote(str(directory / 'objects.sqlite')) + '?mode=ro&immutable=1', uri=True)) as objects:
                objects.execute('PRAGMA trusted_schema=OFF')
                rows = objects.execute('''SELECT o.object_id,o.role,o.geometry_wkb,o.area_m2,o.length_m,o.district_id,
                    o.attribute_status,o.overlap_count,v.properties FROM objects o JOIN attribute_variants v
                    ON v.object_id=o.object_id WHERE v.sha256=(SELECT MIN(sha256) FROM attribute_variants WHERE object_id=o.object_id)
                    ORDER BY o.object_id''')
                for identifier, role, raw, area, length, district, status, overlaps, props in rows:
                    properties = json.loads(props) if status == 'CONSISTENT' else {}
                    body, bounds = display_record(identifier, role, raw, area, length, district, status, overlaps, properties)
                    x, y = body['center']
                    key = f'{math.floor(x / TILE_SIZE)}_{math.floor(y / TILE_SIZE)}'
                    relative_bounds = (bounds[0] - ORIGIN[0], bounds[1] - ORIGIN[1], bounds[2] - ORIGIN[0], bounds[3] - ORIGIN[1])
                    staging.execute('INSERT INTO records VALUES(?,?,?,?,?,?,?)',
                        (key, identifier, source.canonical(body), *relative_bounds))
                    counts[role] += 1
                if sum(counts.values()) != objects.execute('SELECT COUNT(*) FROM objects').fetchone()[0]:
                    raise source.TopographyDataError('지도 속성 대응이 없는 원 객체')
                if sum(counts.values()) != summary['counts']['objects']:
                    raise source.TopographyDataError('객체 요약·지도 객체 수 불일치')
            staging.commit()
            tiles = staging.execute('SELECT tile,COUNT(*),MIN(minx),MIN(miny),MAX(maxx),MAX(maxy) FROM records GROUP BY tile ORDER BY tile').fetchall()
            for key, number, minx, miny, maxx, maxy in tiles:
                features = [json.loads(row[0]) for row in staging.execute('SELECT payload FROM records WHERE tile=? ORDER BY id', (key,))]
                file = 'tiles/' + key + '.json'
                reference = write_json(output / file, {'schemaVersion': 2, 'id': key, 'features': features})
                if reference['bytes'] > 16 * 1024**2:
                    raise source.TopographyDataError('시야별 지도 파일 예산 초과')
                entries.append({'id': key, 'file': file, 'count': number,
                    'bounds': [minx, miny, maxx, maxy], **reference})
                if progress and len(entries) % 100 == 0:
                    progress(len(entries), len(tiles))
        (output / 'staging.sqlite').unlink()
        districts = [{'id': d['id'], 'name': d['name'], 'areaM2': d['areaM2'],
            'center': [d['centerProjected'][0] - ORIGIN[0], d['centerProjected'][1] - ORIGIN[1]],
            'geometry': mapping(translate(shape(d['nativeGeometry']), -ORIGIN[0], -ORIGIN[1]))} for d in boundaries['districts']]
        catalog = {'schemaVersion': 2, 'id': 'seoul-ngii-20260307', 'sourceSpatialSha256': summary['sourceSpatialSha256'],
            'sourceObjectsSha256': summary['objectsSha256'], 'boundaryContentSha256': summary['boundaryContentSha256'],
            'coordinateSystem': 'EPSG:5186', 'originProjected': ORIGIN, 'tileSizeM': TILE_SIZE,
            'distributionUpdatedAt': '2026-03-07', 'districts': districts, 'tiles': entries, 'counts': dict(sorted(counts.items())),
            'attribution': '국토지리정보원 수치지도V2.0 · 브이월드 · 서울특별시/서울신용보증재단 자치구 영역',
            'license': 'KOGL-TYPE1', 'licenseEvidenceUrl': 'https://www.data.go.kr/data/15059719/fileData.do',
            'policy': {'modelCalculationsFromDisplayGeometry': False, 'geometryClippedToTile': False,
                'heightIsSurveyed': False, 'parkingStallsProvided': False, 'unknownOneWayDirectionInferred': False,
                'sourceScaleDenominator': 1000, 'serviceMigrated': False}}
        reference = write_json(output / 'catalog.json', catalog)
        if (any(spatial.file_sha256(path) != code_hashes[key] for key, path in code_paths.items())
                or spatial.file_sha256(directory / 'objects.sqlite') != summary['objectsSha256']):
            raise source.TopographyDataError('지도 생성 중 객체·코드 변경')
        result = {'schemaVersion': 1, 'catalog': reference, **code_hashes,
            'objectsSha256': summary['objectsSha256'], 'sourceSpatialSha256': summary['sourceSpatialSha256'],
            'tileCount': len(entries), 'counts': dict(sorted(counts.items())), 'serviceMigrated': False,
            'versions': {'shapely': shapely.__version__, 'geos': shapely.geos_version_string, 'sqlite': sqlite3.sqlite_version}}
        write_json(output / 'summary.json', result)
        return result
    except BaseException:
        shutil.rmtree(output)
        raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    try:
        result = build(OBJECT_DIRECTORY, native.read_json(BOUNDARIES, limit=4 * 1024**2), args.output.absolute(),
                       progress=lambda done, total: print(f'지도 파일 {done}/{total}', flush=True))
    except source.TopographyDataError as exc:
        parser.exit(1, f'지도 생성 실패: {exc}\n')
    except (OSError, ValueError, KeyError, TypeError, sqlite3.DatabaseError, shapely.errors.ShapelyError):
        parser.exit(1, '지도 생성 실패: 객체·경계·파일 확인 필요\n')
    print(source.canonical(result))


if __name__ == '__main__':
    main()
