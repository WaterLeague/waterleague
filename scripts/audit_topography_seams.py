"""원 도곽선의 서울 피복과 동일 UFID 건물 조각의 접합 근거 검사."""
import argparse
from collections import Counter
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
from urllib.parse import quote

import shapely
from shapely.geometry import shape

import prepare_seoul_spatial as spatial
import prepare_seoul_topography as source
import topography_catalog as native

SOURCE_DIRECTORY = source.ROOT / 'data/private/vworld-seoul-topography-20260307/spatial-v1'
BOUNDARIES = source.ROOT / 'data/derived/seoul-district-boundaries-v1.json'


def connection(catalog):
    value = sqlite3.connect('file:' + quote(str(catalog.database)) + '?mode=ro&immutable=1', uri=True)
    value.execute('PRAGMA trusted_schema=OFF')
    return value


def frame_coverage(catalog, boundaries):
    with closing(connection(catalog)) as database:
        rows = database.execute('''SELECT f.fid,f.tile,f.layer,f.properties,f.geometry_wkb
            FROM layers l CROSS JOIN features f ON f.tile=l.tile AND f.layer=l.layer
            WHERE l.layer IN ('N1A_H0010000','N3A_H0010000') AND f.geometry_status='VALID'
            ORDER BY f.tile,f.layer,f.record_number''').fetchall()
        tiles = {row[0] for row in database.execute('SELECT tile FROM tiles')}
    frames, parts, mismatches = {}, {1000: [], 5000: []}, []
    for fid, tile, layer, properties, raw in rows:
        attributes, geometry = json.loads(properties), shapely.from_wkb(raw)
        scale = 1000 if layer.startswith('N1') else 5000
        parts[scale].append(geometry)
        if attributes.get('도엽코드') != tile:
            mismatches.append(fid)
        if tile in frames:
            raise source.TopographyDataError('한 원본 도엽에 복수 도곽 존재')
        frames[tile] = {'fid': fid, 'scale': scale, 'geometry': geometry,
                        'codeMatches': attributes.get('도엽코드') == tile}
    city = shape(boundaries['boundary'])
    coverage = {scale: shapely.union_all(geometries) for scale, geometries in parts.items()}
    supported = shapely.union_all(list(coverage.values()))
    by_district = {}
    for district in boundaries['districts']:
        boundary = shape(district['nativeGeometry'])
        by_district[district['id']] = {'name': district['name'], 'districtAreaM2': boundary.area,
            'covered1000M2': boundary.intersection(coverage[1000]).area,
            'additional5000M2': boundary.intersection(coverage[5000].difference(coverage[1000])).area,
            'uncoveredM2': boundary.difference(supported).area}
    return frames, {'frameCountByScale': {str(scale): len(value) for scale, value in parts.items()},
        'missingFrameTiles': sorted(tiles - set(frames)), 'frameCodeMismatchFids': mismatches,
        'cityAreaM2': city.area, 'covered1000M2': city.intersection(coverage[1000]).area,
        'additional5000M2': city.intersection(coverage[5000].difference(coverage[1000])).area,
        'uncoveredM2': city.difference(supported).area, 'districts': by_district,
        'coverageMeaning': 'REGISTERED_SHEET_EXTENT_NOT_ALL_FEATURES_PRESENT_OR_FIELD_ACCURACY'}


def compare_pair(first, second, frames):
    a, b = first['geometry'], second['geometry']
    same_attributes = first['attributes'] == second['attributes']
    if shapely.equals_exact(a, b, tolerance=0, normalize=True):
        return 'COINCIDENT_SAME_ATTRIBUTES' if same_attributes else 'COINCIDENT_ATTRIBUTE_CONFLICT'
    if first['tile'] == second['tile']:
        return 'SAME_TILE_DIFFERENT_RECORDS'
    if not same_attributes:
        return 'ATTRIBUTE_CONFLICT'
    if a.intersection(b).area > 0:
        return 'POSITIVE_AREA_OVERLAP'
    shared = a.boundary.intersection(b.boundary)
    if shared.length <= 0:
        return 'NO_SHARED_EDGE'
    frame_a, frame_b = frames.get(first['tile']), frames.get(second['tile'])
    if (frame_a is None or frame_b is None or not frame_a['codeMatches'] or not frame_b['codeMatches']
            or frame_a['scale'] != frame_b['scale']):
        return 'FRAME_NOT_VERIFIED'
    if not frame_a['geometry'].boundary.covers(shared) or not frame_b['geometry'].boundary.covers(shared):
        return 'NOT_ON_BOTH_ORIGINAL_FRAME_EDGES'
    joined = shapely.union_all([a, b])
    if not joined.is_valid or not abs(joined.area - a.area - b.area) <= 1e-7:
        return 'JOIN_NOT_AREA_PRESERVING'
    return 'VERIFIED_DISJOINT_FRAGMENT_EDGE'


def audit(catalog, boundaries):
    code_sha = spatial.file_sha256(__file__)
    boundary_sha = source.digest(source.canonical(boundaries).encode())
    frames, coverage = frame_coverage(catalog, boundaries)
    counts, details = Counter(), []
    with closing(connection(catalog)) as database:
        groups = database.execute('''SELECT GROUP_CONCAT(f.fid) FROM layers l CROSS JOIN features f
            ON f.tile=l.tile AND f.layer=l.layer WHERE l.role='BUILDING_FOOTPRINT' AND l.scale_denominator=1000
            AND f.geometry_status='VALID' AND json_extract(f.properties,'$.UFID') IS NOT NULL
            GROUP BY json_extract(f.properties,'$.UFID') HAVING COUNT(*)>1''').fetchall()
        for group in groups:
            fids = sorted(map(int, group[0].split(',')))
            if len(fids) > 1000:
                raise source.TopographyDataError('동일 UFID 대조 집합 크기 초과')
            placeholders = ','.join('?' for _ in fids)
            records = database.execute(f'''SELECT fid,tile,properties,geometry_wkb FROM features
                WHERE fid IN ({placeholders}) ORDER BY fid''', fids).fetchall()
            parsed = []
            for fid, tile, attributes, wkb in records:
                attributes = json.loads(attributes)
                attributes.pop('UFID', None)
                parsed.append({'fid': fid, 'tile': tile, 'attributes': attributes, 'geometry': shapely.from_wkb(wkb)})
            for index, first in enumerate(parsed):
                for second in parsed[index + 1:]:
                    classification = compare_pair(first, second, frames)
                    counts[classification] += 1
                    details.append({'firstFid': first['fid'], 'secondFid': second['fid'], 'classification': classification})
    if (spatial.file_sha256(__file__) != code_sha
            or spatial.file_sha256(catalog.database) != catalog.summary['spatialSha256']
            or source.digest(source.canonical(boundaries).encode()) != boundary_sha):
        raise source.TopographyDataError('접합 검사 중 코드·원본·경계 변경')
    return {'schemaVersion': 1, 'sourceSpatialSha256': catalog.summary['spatialSha256'],
        'boundaryContentSha256': boundary_sha,
        'generatorSha256': code_sha, 'coverage': coverage,
        'buildingRepeatedUfidGroups': len(groups), 'buildingPairCounts': dict(sorted(counts.items())),
        'buildingPairs': details, 'policy': {'ufidOnlyMerging': False, 'geometryRepair': False,
            'coordinateSnapping': False, 'boundaryClipsHydrology': False, 'joinsApplied': False,
            'fieldAccuracyVerified': False, 'serviceMigrated': False}}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        if os.path.lexists(args.output):
            raise source.TopographyDataError('기존 접합 검사 덮어쓰기 금지')
        expected = native.read_json(source.ROOT / 'data/manifests/seoul-spatial-catalog-v1.json')
        catalog = native.SpatialCatalog(SOURCE_DIRECTORY, expected)
        result = audit(catalog, native.read_json(BOUNDARIES, limit=4 * 1024**2))
        with args.output.open('x', encoding='utf-8') as stream:
            stream.write(source.canonical(result) + '\n')
    except source.TopographyDataError as exc:
        parser.exit(1, f'도엽 접합 검사 실패: {exc}\n')
    except (OSError, ValueError, KeyError, sqlite3.DatabaseError, shapely.errors.ShapelyError):
        parser.exit(1, '도엽 접합 검사 실패: 입력·도곽·경계 확인 필요\n')
    print(source.canonical({key: result[key] for key in ['buildingRepeatedUfidGroups', 'buildingPairCounts']}))
    print(source.canonical({key: value for key, value in result['coverage'].items() if key != 'districts'}))


if __name__ == '__main__':
    main()
