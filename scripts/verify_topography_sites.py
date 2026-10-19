"""설계 영역 전체의 원형 대응·구멍 면적·제외 영역·중복 배분 대조."""
import argparse
from contextlib import closing
from decimal import Decimal
import json
import math
import os
from pathlib import Path
import sqlite3

import shapely

import prepare_seoul_spatial as spatial
import prepare_seoul_topography as source
import prepare_topography_sites as sites
import topography_catalog as native

TOLERANCE_M2 = 1e-7


def verify(directory, objects_directory, spatial_catalog, progress=None, boundaries=None):
    report = native.read_json(directory / 'summary.json')
    objects_report = native.read_json(objects_directory / 'summary.json')
    if (report['sourceObjectsSha256'] != objects_report['objectsSha256']
            or report['sourceSpatialSha256'] != spatial_catalog.summary['spatialSha256']):
        raise source.TopographyDataError('설계 영역 대조의 원본 버전 불일치')
    if boundaries is None:
        boundaries = native.read_json(sites.objects.BOUNDARIES, limit=4 * 1024**2)
    if source.digest(source.canonical(boundaries).encode()) != report['boundaryContentSha256']:
        raise source.TopographyDataError('설계 영역 대조의 자치구 경계 불일치')
    assignment = sites.objects.DistrictAssignment(boundaries)
    database_path = directory / 'sites.sqlite'
    objects_path = objects_directory / 'objects.sqlite'
    for path, checksum in [(database_path, report['sitesSha256']), (objects_path, report['sourceObjectsSha256'])]:
        with source.source_stream(path, expected_sha256=checksum, limit=16 * 1024**3):
            pass
    code_sha = spatial.file_sha256(__file__)
    mask_index = sites.Exclusions(spatial_catalog.database)
    counts = {'ROOF': 0, 'GROUND': 0, 'holes': 0, 'multipart': 0}
    with closing(sites.connect(database_path)) as database:
        database.execute('ATTACH DATABASE ? AS originals', ('file:' + str(objects_path) + '?mode=ro&immutable=1',))
        if database.execute('PRAGMA integrity_check').fetchone() != ('ok',) or database.execute('PRAGMA foreign_key_check').fetchone():
            raise source.TopographyDataError('설계 영역 무결성·원형 참조 대조 실패')
        if database.execute('''SELECT COUNT(*) FROM decisions d LEFT JOIN originals.objects o
                ON o.object_id=d.object_id WHERE o.object_id IS NULL OR o.role!=d.role''').fetchone()[0]:
            raise source.TopographyDataError('원본에 없는 설계 영역 판정')
        if database.execute('''SELECT COUNT(*) FROM candidates c JOIN decisions d ON c.object_id=d.object_id
                WHERE d.status!='CANDIDATE' OR c.role!=d.role''').fetchone()[0]:
            raise source.TopographyDataError('제외 판정을 설계 영역으로 반환')
        rows = database.execute('''SELECT c.fid,c.id,c.kind,c.geometry_wkb,c.area_m2,c.max_area_m2,
            c.source_area_m2,c.removed_area_m2,c.method,c.object_id,c.geometry_sha256,
            o.geometry_wkb,o.area_m2,o.overlap_count,o.attribute_status,c.role,c.district_id,c.district_intersections,
            (SELECT json_extract(v.properties,'$.종류') FROM originals.attribute_variants v
             WHERE v.object_id=c.object_id ORDER BY v.sha256 LIMIT 1)
            FROM candidates c JOIN originals.objects o ON o.object_id=c.object_id ORDER BY c.fid''')
        for index, row in enumerate(rows, 1):
            (fid, identifier, kind, raw, area, limit, source_area, removed, method, object_id, checksum,
             original_raw, original_area, overlaps, state, role, district, district_parts, building_kind) = row
            geometry, original = shapely.from_wkb(raw), shapely.from_wkb(original_raw)
            expected_id, expected_checksum = sites.candidate_key(object_id, geometry)
            expected_district, expected_parts = assignment.assign(geometry)
            if (not geometry.is_valid or geometry.is_empty or geometry.geom_type not in ('Polygon', 'MultiPolygon')
                    or expected_id != identifier or expected_checksum != checksum or state != 'CONSISTENT'
                    or source_area != original_area or area != geometry.area
                    or not math.isclose(source_area - area, removed, abs_tol=1e-6, rel_tol=1e-10)
                    or Decimal(limit) != sites.site_geometry.area_limit(geometry)
                    or geometry.difference(original).area > TOLERANCE_M2
                    or district != expected_district or json.loads(district_parts) != expected_parts):
                raise source.TopographyDataError('설계 영역의 원형·식별·면적 결속 불일치')
            if kind == 'ROOF':
                if (raw != original_raw or overlaps or method != 'ORIGINAL_BUILDING_FOOTPRINT'
                        or role != 'BUILDING_FOOTPRINT' or building_kind not in sites.ROOF_KINDS):
                    raise source.TopographyDataError('옥상 원형 변경·겹침 승인')
            elif kind == 'GROUND':
                if method != 'ORIGINAL_SURFACE_MINUS_EXCLUSIONS' or role not in sites.GROUND_ROLES:
                    raise source.TopographyDataError('지상 제외 방법 불일치')
                masks, _, invalid = mask_index.query(geometry)
                if invalid or any(geometry.intersection(mask).area > TOLERANCE_M2 for mask in masks):
                    raise source.TopographyDataError('제외 구조물·수면·원 오류 영역에 설계 영역 잔존')
                a, b, c, d = geometry.bounds
                for other_raw, in database.execute('''SELECT c.geometry_wkb FROM candidate_bounds b
                    CROSS JOIN candidates c ON c.fid=b.fid WHERE b.maxx>=? AND b.minx<=?
                    AND b.maxy>=? AND b.miny<=? AND c.kind='GROUND' AND c.fid>?''', (a, c, b, d, fid)):
                    if geometry.intersection(shapely.from_wkb(other_raw)).area > TOLERANCE_M2:
                        raise source.TopographyDataError('지상 설계 영역의 면적 중복 배분')
            else:
                raise source.TopographyDataError('설계 영역 종류 미등록')
            counts[kind] += 1
            parts = [geometry] if geometry.geom_type == 'Polygon' else list(geometry.geoms)
            counts['holes'] += sum(len(part.interiors) for part in parts)
            counts['multipart'] += geometry.geom_type == 'MultiPolygon'
            if progress and index % 100_000 == 0:
                progress(index)
        if any(counts[kind] != report['counts'].get(kind, 0) for kind in ('ROOF', 'GROUND')):
            raise source.TopographyDataError('설계 영역 종류별 집계 불일치')
        if database.execute('SELECT COUNT(*) FROM decisions').fetchone()[0] != report['counts']['sourceRecords']:
            raise source.TopographyDataError('원 객체 판정 누락')
    for path, checksum in [(database_path, report['sitesSha256']), (objects_path, report['sourceObjectsSha256']),
                           (spatial_catalog.database, report['sourceSpatialSha256'])]:
        if spatial.file_sha256(path) != checksum:
            raise source.TopographyDataError('설계 영역 대조 중 입력 변경')
    if spatial.file_sha256(__file__) != code_sha:
        raise source.TopographyDataError('설계 영역 대조 중 코드 변경')
    return {'schemaVersion': 1, 'status': 'PASS', 'verifierSha256': code_sha,
        'sitesSha256': report['sitesSha256'], 'sourceObjectsSha256': report['sourceObjectsSha256'],
        'sourceSpatialSha256': report['sourceSpatialSha256'], 'counts': counts,
        'overlayAreaToleranceM2': TOLERANCE_M2, 'positiveAreaGroundOverlaps': 0,
        'constructionApprovalVerified': False, 'facilityAndCostBindingComplete': False,
        'serviceMigrated': False, 'versions': {'shapely': shapely.__version__, 'geos': shapely.geos_version_string}}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--sites', type=Path, default=sites.OUTPUT)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        if os.path.lexists(args.output):
            raise source.TopographyDataError('기존 설계 영역 대조 덮어쓰기 금지')
        catalog = native.SpatialCatalog(sites.ROOT / 'spatial-v1', native.read_json(source.ROOT / 'data/manifests/seoul-spatial-catalog-v1.json'))
        result = verify(args.sites, sites.ROOT / 'objects-v1', catalog,
                        progress=lambda done: print(f'설계 영역 대조 {done}', flush=True))
        with args.output.open('x', encoding='utf-8') as stream:
            stream.write(source.canonical(result) + '\n')
    except source.TopographyDataError as exc:
        parser.exit(1, f'설계 영역 대조 실패: {exc}\n')
    except (OSError, ValueError, KeyError, TypeError, sqlite3.DatabaseError, shapely.errors.ShapelyError):
        parser.exit(1, '설계 영역 대조 실패: 원형·면적·제외 근거 확인 필요\n')
    print(source.canonical(result))


if __name__ == '__main__':
    main()
