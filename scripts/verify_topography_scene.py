"""지도 파일 전체의 원 객체 대응·형상·면적·타일 경계 독립 대조."""
import argparse
from collections import Counter
from contextlib import closing
import json
import math
import os
from pathlib import Path
import sqlite3
from urllib.parse import quote

import shapely
from shapely.affinity import translate
from shapely.geometry import shape

import prepare_seoul_spatial as spatial
import prepare_seoul_topography as source
import topography_catalog as native

ROOT = source.ROOT / 'data/private/vworld-seoul-topography-20260307'


def compare(feature, record, origin):
    role, raw, area, length, district, attribute_status, overlaps = record
    original = shapely.from_wkb(raw)
    restored = translate(shape(feature['geometry']), origin[0], origin[1])
    if (not restored.is_valid or not restored.equals_exact(original, tolerance=1e-8)
            or feature['role'] != role or feature['districtId'] != district
            or feature['sourceAreaM2'] != area or feature['sourceLengthM'] != length
            or area is not None and not math.isclose(restored.area, area, abs_tol=1e-6, rel_tol=1e-10)
            or length is not None and not math.isclose(restored.length, length, abs_tol=1e-6, rel_tol=1e-10)):
        raise source.TopographyDataError('지도와 원 객체 형상·역할·소속·면적 불일치')
    expected = 'ATTRIBUTE_CONFLICT' if attribute_status != 'CONSISTENT' else 'UNRESOLVED_OVERLAP' if overlaps else 'GEOMETRY_ONLY'
    if feature['geometryEligibility'] != expected or feature['constructionEligibility'] != 'UNKNOWN':
        raise source.TopographyDataError('지도 객체의 배치·시공 확인 상태 불일치')
    center = shapely.Point(feature['center'][0] + origin[0], feature['center'][1] + origin[1])
    if original.distance(center) > 1e-8:
        raise source.TopographyDataError('지도 중심점이 원 도형 밖에 위치')
    return shape(feature['geometry']).bounds


def verify(directory, objects_directory, progress=None):
    code_sha = spatial.file_sha256(__file__)
    summary = native.read_json(directory / 'summary.json')
    objects_summary = native.read_json(objects_directory / 'summary.json')
    if summary['objectsSha256'] != objects_summary['objectsSha256']:
        raise source.TopographyDataError('지도·객체 입력 버전 불일치')
    with source.source_stream(directory / 'catalog.json', summary['catalog']['bytes'], summary['catalog']['sha256']) as (stream, _):
        catalog = json.load(stream)
    if (catalog['sourceObjectsSha256'] != summary['objectsSha256']
            or catalog['sourceSpatialSha256'] != objects_summary['sourceSpatialSha256']
            or catalog['boundaryContentSha256'] != objects_summary['boundaryContentSha256']):
        raise source.TopographyDataError('지도 출처 해시 불일치')
    database_path = objects_directory / 'objects.sqlite'
    with source.source_stream(database_path, expected_sha256=summary['objectsSha256'], limit=16 * 1024**3):
        pass
    identifiers, counts = set(), Counter()
    maximum_bytes, total_bytes = 0, 0
    with closing(sqlite3.connect('file:' + quote(str(database_path)) + '?mode=ro&immutable=1', uri=True)) as database:
        database.execute('PRAGMA trusted_schema=OFF')
        for index, entry in enumerate(catalog['tiles']):
            path = source.project_path(directory, entry['file'])
            with source.source_stream(path, entry['bytes'], entry['sha256'], limit=16 * 1024**2) as (stream, _):
                tile = json.load(stream)
            if tile['id'] != entry['id'] or tile['schemaVersion'] != 2 or len(tile['features']) != entry['count']:
                raise source.TopographyDataError('지도 파일 식별·객체 수 불일치')
            # 청크 조회는 SQLite의 바인딩 한도를 넘지 않으면서 원 객체 누락을 검사한다.
            names = [f['id'] for f in tile['features']]
            originals = {}
            for start in range(0, len(names), 500):
                selected = names[start:start + 500]
                placeholders = ','.join('?' for _ in selected)
                originals.update((row[0], row[1:]) for row in database.execute(f'''SELECT object_id,role,
                    geometry_wkb,area_m2,length_m,district_id,attribute_status,overlap_count FROM objects
                    WHERE object_id IN ({placeholders})''', selected))
            bounds = []
            for feature in tile['features']:
                identifier = feature['id']
                if identifier in identifiers or identifier not in originals:
                    raise source.TopographyDataError('중복되거나 원본에 없는 지도 객체')
                identifiers.add(identifier)
                bounds.append(compare(feature, originals[identifier], catalog['originProjected']))
                x, y = feature['center']
                expected_tile = f"{math.floor(x / catalog['tileSizeM'])}_{math.floor(y / catalog['tileSizeM'])}"
                if expected_tile != entry['id']:
                    raise source.TopographyDataError('지도 중심점·시야 파일 배정 불일치')
                counts[feature['role']] += 1
            combined = [min(b[0] for b in bounds), min(b[1] for b in bounds),
                        max(b[2] for b in bounds), max(b[3] for b in bounds)]
            if combined != entry['bounds']:
                raise source.TopographyDataError('시야 조회 범위가 원 객체 경계를 누락')
            maximum_bytes = max(maximum_bytes, entry['bytes'])
            total_bytes += entry['bytes']
            if progress and (index + 1) % 100 == 0:
                progress(index + 1, len(catalog['tiles']))
        if len(identifiers) != database.execute('SELECT COUNT(*) FROM objects').fetchone()[0] or dict(counts) != catalog['counts']:
            raise source.TopographyDataError('지도 전체 객체·역할 수 누락')
    if (spatial.file_sha256(database_path) != summary['objectsSha256']
            or spatial.file_sha256(directory / 'catalog.json') != summary['catalog']['sha256']
            or spatial.file_sha256(__file__) != code_sha):
        raise source.TopographyDataError('지도 대조 중 입력·코드 변경')
    return {'schemaVersion': 1, 'status': 'PASS', 'verifierSha256': code_sha,
        'catalogSha256': summary['catalog']['sha256'], 'objectsSha256': summary['objectsSha256'],
        'tileCount': len(catalog['tiles']), 'objectsCompared': len(identifiers),
        'coordinateToleranceM': 1e-8, 'measureAbsoluteTolerance': 1e-6, 'measureRelativeTolerance': 1e-10,
        'totalTileBytes': total_bytes, 'maximumTileBytes': maximum_bytes,
        'browserPerformanceVerified': False, 'fieldAccuracyVerified': False,
        'versions': {'shapely': shapely.__version__, 'geos': shapely.geos_version_string, 'sqlite': sqlite3.sqlite_version}}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--scene', type=Path, default=ROOT / 'scene-v1')
    parser.add_argument('--objects', type=Path, default=ROOT / 'objects-v1')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        if os.path.lexists(args.output):
            raise source.TopographyDataError('기존 지도 대조 결과 덮어쓰기 금지')
        result = verify(args.scene, args.objects, progress=lambda done, total:
                        print(f'원 객체 대조 {done}/{total}', flush=True))
        with args.output.open('x', encoding='utf-8') as stream:
            stream.write(source.canonical(result) + '\n')
    except source.TopographyDataError as exc:
        parser.exit(1, f'지도 대조 실패: {exc}\n')
    except (OSError, ValueError, KeyError, TypeError, sqlite3.DatabaseError, shapely.errors.ShapelyError):
        parser.exit(1, '지도 대조 실패: 입력·객체·형상 확인 필요\n')
    print(source.canonical(result))


if __name__ == '__main__':
    main()
