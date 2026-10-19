"""원 공간 객체에서 중복 없는 옥상·지상 설계 영역과 제외 근거 생성."""
import argparse
from collections import Counter
from contextlib import closing
import json
import math
import os
from pathlib import Path
import shutil
import sqlite3
import sys
from urllib.parse import quote

import shapely
from shapely.geometry import box
from shapely.strtree import STRtree

import prepare_seoul_spatial as spatial
import prepare_seoul_topography as source
import prepare_topography_objects as objects
import topography_catalog as native

sys.path.insert(0, str(source.ROOT / 'simulation'))
from waterleague_sim.spatial import geometry as site_geometry

ROOT = source.ROOT / 'data/private/vworld-seoul-topography-20260307'
OUTPUT = ROOT / 'sites-v1'
GROUND_ROLES = ('SIDEWALK_AREA', 'ROAD_AREA', 'CULTIVATION_LANDSCAPE_AREA')
ROOF_KINDS = {'아파트', '연립주택', '일반주택', '주택외건물'}
MASK_ROLES = ('BUILDING_FOOTPRINT', 'BRIDGE_AREA', 'TUNNEL_AREA', 'RAILWAY_AREA',
    'RIVER_WATER_AREA', 'LAKE_RESERVOIR_AREA', 'CROSSWALK_AREA', 'TRAFFIC_SAFETY_AREA',
    'PEDESTRIAN_OVERPASS_AREA', 'INTERSECTION_AREA', 'GRADE_SEPARATED_INTERSECTION_AREA', 'INTERCHANGE_AREA')


def connect(path):
    value = sqlite3.connect('file:' + quote(str(path)) + '?mode=ro&immutable=1', uri=True)
    value.execute('PRAGMA trusted_schema=OFF')
    return value


class Exclusions:
    def __init__(self, database):
        selected_roles = tuple(dict.fromkeys((*MASK_ROLES, *GROUND_ROLES)))
        roles = ','.join('?' for _ in selected_roles)
        sql = f'''SELECT f.fid,l.role,f.geometry_status,f.geometry_wkb,f.minx,f.miny,f.maxx,f.maxy
            FROM layers l CROSS JOIN features f ON f.tile=l.tile AND f.layer=l.layer
            WHERE l.role IN ({roles}) AND l.scale_denominator=1000 AND f.deleted=0 ORDER BY f.fid'''
        self.ids, self.geometries, self.invalid_ids, self.invalid_bounds = [], [], [], []
        with closing(connect(database)) as connection:
            for fid, role, status, raw, *bounds in connection.execute(sql, selected_roles):
                if status == 'VALID':
                    if role not in MASK_ROLES:
                        continue
                    geometry = shapely.from_wkb(raw)
                    if geometry.geom_type not in ('Polygon', 'MultiPolygon'):
                        raise source.TopographyDataError('제외 역할의 면 도형 불일치')
                    self.ids.append(fid)
                    self.geometries.append(geometry)
                else:
                    if any(v is None for v in bounds):
                        raise source.TopographyDataError('잘못된 제외 도형의 영향 범위 미확인')
                    self.invalid_ids.append(fid)
                    self.invalid_bounds.append(box(*bounds))
        self.tree = STRtree(self.geometries)
        self.invalid_tree = STRtree(self.invalid_bounds)

    def query(self, geometry):
        invalid = sorted(self.invalid_ids[int(i)] for i in self.invalid_tree.query(geometry, predicate='intersects'))
        if invalid:
            return [], [('INVALID_NATIVE_FEATURE', str(fid)) for fid in invalid], True
        indices = sorted(map(int, self.tree.query(geometry, predicate='intersects')))
        selected = [i for i in indices if geometry.intersection(self.geometries[i]).area > 0]
        return [self.geometries[i] for i in selected], [('NATIVE_FEATURE', str(self.ids[i])) for i in selected], False


def candidate_key(object_id, geometry):
    checksum = source.digest(shapely.to_wkb(shapely.normalize(geometry), byte_order=1))
    return 'C' + source.digest((object_id + ':' + checksum).encode())[:24], checksum


def ground_geometry(original, masks):
    result = original.difference(shapely.union_all(masks)) if masks else original
    if result.is_empty or result.area <= 0:
        return None
    if (result.geom_type not in ('Polygon', 'MultiPolygon') or not result.is_valid
            or result.area > original.area + 1e-7 or result.difference(original).area > 1e-7):
        raise source.TopographyDataError('지상 제외 연산의 원 영역·유효성 보존 실패')
    if any(result.intersection(mask).area > 1e-7 for mask in masks):
        raise source.TopographyDataError('지상 제외 영역의 양의 면적 잔존')
    return result


def prepare_database(database):
    database.executescript('''PRAGMA foreign_keys=ON;PRAGMA page_size=4096;PRAGMA cache_size=-65536;
        PRAGMA user_version=1;
        CREATE TABLE decisions(object_id TEXT PRIMARY KEY,role TEXT NOT NULL,status TEXT NOT NULL,
            evidence TEXT NOT NULL) WITHOUT ROWID;
        CREATE TABLE candidates(fid INTEGER PRIMARY KEY,id TEXT UNIQUE NOT NULL,object_id TEXT UNIQUE NOT NULL
            REFERENCES decisions(object_id),district_id TEXT NOT NULL,kind TEXT NOT NULL,role TEXT NOT NULL,
            geometry_wkb BLOB NOT NULL,geometry_sha256 TEXT NOT NULL,area_m2 REAL NOT NULL,
            max_area_m2 TEXT NOT NULL,source_area_m2 REAL NOT NULL,removed_area_m2 REAL NOT NULL,
            method TEXT NOT NULL,district_intersections TEXT NOT NULL);
        CREATE VIRTUAL TABLE candidate_bounds USING rtree(fid,minx,maxx,miny,maxy);
        CREATE TABLE exclusions(object_id TEXT REFERENCES decisions(object_id),kind TEXT NOT NULL,
            mask_id TEXT NOT NULL,PRIMARY KEY(object_id,kind,mask_id)) WITHOUT ROWID;
        CREATE INDEX candidate_district ON candidates(district_id,kind);
    ''')


def previous_ground(database, geometry):
    a, b, c, d = geometry.bounds
    rows = database.execute('''SELECT c.id,c.geometry_wkb FROM candidate_bounds b CROSS JOIN candidates c
        ON c.fid=b.fid WHERE b.maxx>=? AND b.minx<=? AND b.maxy>=? AND b.miny<=? AND c.kind='GROUND'
        ORDER BY c.id''', (a, c, b, d))
    selected, links = [], []
    for identifier, raw in rows:
        other = shapely.from_wkb(raw)
        if geometry.intersection(other).area > 0:
            selected.append(other)
            links.append(('PRIOR_GROUND_CANDIDATE', identifier))
    return selected, links


def build(directory, spatial_catalog, boundaries, output, progress=None):
    if os.path.lexists(output) or output.parent.resolve() != output.parent.absolute():
        raise source.TopographyDataError('기존 후보 출력·출력 링크 덮어쓰기 금지')
    summary = native.read_json(directory / 'summary.json')
    if (summary['sourceSpatialSha256'] != spatial_catalog.summary['spatialSha256']
            or summary['boundaryContentSha256'] != source.digest(source.canonical(boundaries).encode())):
        raise source.TopographyDataError('후보 객체·원본·자치구 경계 버전 불일치')
    with source.source_stream(directory / 'objects.sqlite', expected_sha256=summary['objectsSha256'], limit=16 * 1024**3):
        pass
    files = {'generatorSha256': Path(__file__), 'geometryCodeSha256': Path(site_geometry.__file__),
             'assignmentCodeSha256': Path(objects.__file__), 'sourceReaderSha256': Path(source.__file__),
             'decoderSha256': Path(native.__file__)}
    code_hashes = {key: spatial.file_sha256(path) for key, path in files.items()}
    assignments, masks = objects.DistrictAssignment(boundaries), Exclusions(spatial_catalog.database)
    output.mkdir(mode=0o700)
    counts, by_district = Counter(), Counter()
    try:
        with closing(connect(directory / 'objects.sqlite')) as originals, closing(sqlite3.connect(output / 'sites.sqlite')) as target:
            prepare_database(target)
            for role in ('BUILDING_FOOTPRINT', *GROUND_ROLES):
                rows = originals.execute('''SELECT o.object_id,o.geometry_wkb,o.area_m2,o.attribute_status,
                    o.overlap_count,v.properties FROM objects o JOIN attribute_variants v ON v.object_id=o.object_id
                    WHERE o.role=? AND v.sha256=(SELECT MIN(sha256) FROM attribute_variants WHERE object_id=o.object_id)
                    ORDER BY o.object_id''', (role,))
                for object_id, raw, source_area, status, overlaps, attributes in rows:
                    geometry, props, links = shapely.from_wkb(raw), json.loads(attributes), []
                    if not math.isclose(geometry.area, source_area, rel_tol=1e-10, abs_tol=1e-6):
                        raise source.TopographyDataError('후보 원 객체 면적 불일치')
                    decision, candidate = 'CANDIDATE', None
                    if status != 'CONSISTENT':
                        decision = 'ATTRIBUTE_CONFLICT'
                    elif role == 'BUILDING_FOOTPRINT':
                        if overlaps:
                            decision = 'UNRESOLVED_BUILDING_OVERLAP'
                        elif props.get('종류') not in ROOF_KINDS:
                            decision = 'ROOF_NOT_CONFIRMED_KIND'
                        else:
                            candidate = geometry
                    else:
                        try:
                            excluding, links, invalid = masks.query(geometry)
                            if invalid:
                                decision = 'INVALID_MASK_INFLUENCE'
                            else:
                                previous, references = previous_ground(target, geometry)
                                links.extend(references)
                                candidate = ground_geometry(geometry, excluding + previous)
                                if candidate is None:
                                    decision = 'COVERED_BY_EXCLUSIONS'
                        except (source.TopographyDataError, shapely.errors.ShapelyError):
                            decision = 'OVERLAY_FAILED'
                    if candidate is not None:
                        limit = site_geometry.area_limit(candidate)
                        district, intersections = assignments.assign(candidate)
                        if limit <= 0:
                            decision, candidate = 'MIN_AREA_NOT_REPRESENTABLE', None
                        elif district is None:
                            decision, candidate = 'OUTSIDE_DISTRICT_SCOPE', None
                    evidence = {'buildingKind': props.get('종류') if role == 'BUILDING_FOOTPRINT' else None,
                                'sourceOverlapCount': overlaps, 'constructionEligibility': 'UNKNOWN'}
                    target.execute('INSERT INTO decisions VALUES(?,?,?,?)', (object_id, role, decision, source.canonical(evidence)))
                    target.executemany('INSERT INTO exclusions VALUES(?,?,?)', [(object_id, kind, identifier) for kind, identifier in links])
                    counts[decision] += 1
                    counts['sourceRecords'] += 1
                    if candidate is not None:
                        identifier, checksum = candidate_key(object_id, candidate)
                        kind = 'ROOF' if role == 'BUILDING_FOOTPRINT' else 'GROUND'
                        method = 'ORIGINAL_BUILDING_FOOTPRINT' if kind == 'ROOF' else 'ORIGINAL_SURFACE_MINUS_EXCLUSIONS'
                        cursor = target.execute('''INSERT INTO candidates(id,object_id,district_id,kind,role,geometry_wkb,
                            geometry_sha256,area_m2,max_area_m2,source_area_m2,removed_area_m2,method,district_intersections)
                            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)''', (identifier, object_id, district, kind, role,
                            shapely.to_wkb(candidate, byte_order=1), checksum, candidate.area, str(limit), source_area,
                            source_area - candidate.area, method, source.canonical(intersections)))
                        a, b, c, d = candidate.bounds
                        target.execute('INSERT INTO candidate_bounds VALUES(?,?,?,?,?)', (cursor.lastrowid, a, c, b, d))
                        counts[kind] += 1
                        by_district[district + ':' + kind] += 1
                    if progress and counts['sourceRecords'] % 100_000 == 0:
                        progress(role, dict(counts))
                if progress:
                    progress(role, dict(counts))
            placeholders = ','.join('?' for _ in GROUND_ROLES)
            expected_count = originals.execute(f"SELECT COUNT(*) FROM objects WHERE role='BUILDING_FOOTPRINT' OR role IN ({placeholders})", GROUND_ROLES).fetchone()[0]
            if counts['sourceRecords'] != expected_count:
                raise source.TopographyDataError('설계 영역의 원 객체 속성 대응 누락')
            target.commit()
            target.execute('ANALYZE')
            target.execute('VACUUM')
            if target.execute('PRAGMA integrity_check').fetchone() != ('ok',) or target.execute('PRAGMA foreign_key_check').fetchone():
                raise source.TopographyDataError('설계 영역 원본 대응·무결성 오류')
        if (any(spatial.file_sha256(path) != code_hashes[key] for key, path in files.items())
                or spatial.file_sha256(directory / 'objects.sqlite') != summary['objectsSha256']
                or spatial.file_sha256(spatial_catalog.database) != summary['sourceSpatialSha256']):
            raise source.TopographyDataError('설계 영역 생성 중 코드·입력 변경')
        report = {'schemaVersion': 1, 'status': 'GEOMETRY_CANDIDATES_NOT_SERVICE_MIGRATED',
            'sourceSpatialSha256': summary['sourceSpatialSha256'], 'sourceObjectsSha256': summary['objectsSha256'],
            'boundaryContentSha256': summary['boundaryContentSha256'], **code_hashes,
            'sitesSha256': spatial.file_sha256(output / 'sites.sqlite'), 'sitesBytes': (output / 'sites.sqlite').stat().st_size,
            'counts': dict(sorted(counts.items())), 'districtKindCounts': dict(sorted(by_district.items())),
            'policy': {'groundPriority': list(GROUND_ROLES), 'maskRoles': list(MASK_ROLES), 'scaleDenominator': 1000,
                'overlayAreaToleranceM2': 1e-7,
                'geometryRepair': False, 'clipsToDistrict': False, 'roofKindIsStructuralApproval': False,
                'constructionEligibility': 'UNKNOWN', 'facilityAndCostBindingComplete': False, 'serviceMigrated': False},
            'versions': {'shapely': shapely.__version__, 'geos': shapely.geos_version_string, 'sqlite': sqlite3.sqlite_version}}
        with (output / 'summary.json').open('x', encoding='utf-8') as stream:
            stream.write(source.canonical(report) + '\n')
        return report
    except BaseException:
        shutil.rmtree(output)
        raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    try:
        catalog = native.SpatialCatalog(ROOT / 'spatial-v1', native.read_json(source.ROOT / 'data/manifests/seoul-spatial-catalog-v1.json'))
        expected = native.read_json(source.ROOT / 'data/manifests/seoul-topography-objects-v1.json')
        actual = native.read_json(ROOT / 'objects-v1/summary.json')
        if any(actual[key] != expected[key] for key in ('objectsSha256', 'sourceSpatialSha256', 'boundaryContentSha256', 'generatorSha256')):
            raise source.TopographyDataError('공개 공간 객체 요약 불일치')
        result = build(ROOT / 'objects-v1', catalog, native.read_json(objects.BOUNDARIES, limit=4 * 1024**2), args.output.absolute(),
                       progress=lambda role, counts: print(source.canonical({'role': role, 'counts': counts}), flush=True))
    except source.TopographyDataError as exc:
        parser.exit(1, f'설계 영역 생성 실패: {exc}\n')
    except (OSError, ValueError, KeyError, TypeError, sqlite3.DatabaseError, shapely.errors.ShapelyError):
        parser.exit(1, '설계 영역 생성 실패: 입력·원형·제외 근거 확인 필요\n')
    print(source.canonical({'sitesSha256': result['sitesSha256'], 'counts': result['counts']}))


if __name__ == '__main__':
    main()
