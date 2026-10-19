"""원 공간 객체의 정확히 겹친 도형을 묶고 원본 대응·배치 제약 보존."""
import argparse
from collections import Counter
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
from urllib.parse import quote

import shapely
from shapely.geometry import shape
from shapely.strtree import STRtree

import prepare_seoul_topography as source
import prepare_seoul_spatial as spatial
import topography_catalog as native

OUTPUT = source.ROOT / 'data/private/vworld-seoul-topography-20260307/objects-v1'
BOUNDARIES = source.ROOT / 'data/derived/seoul-district-boundaries-v1.json'
ROLES = ['BUILDING_FOOTPRINT', 'ROAD_AREA', 'ROAD_CENTERLINE', 'SIDEWALK_AREA', 'BRIDGE_AREA',
         'TUNNEL_AREA', 'RAILWAY_AREA', 'RAIL_CENTERLINE', 'RIVER_WATER_AREA', 'LAKE_RESERVOIR_AREA',
         'CULTIVATION_LANDSCAPE_AREA']


def object_key(layer, geometry):
    normalized = shapely.to_wkb(shapely.normalize(geometry), byte_order=1)
    return f'ngii:{layer}:{source.digest(normalized)}'


class DistrictAssignment:
    def __init__(self, boundaries):
        self.entries = sorted(boundaries['districts'], key=lambda d: d['id'])
        self.geometries = [shape(d['nativeGeometry']) for d in self.entries]
        if any(g.is_empty or not g.is_valid for g in self.geometries):
            raise source.TopographyDataError('자치구 집계 경계 오류')
        self.tree = STRtree(self.geometries)
        for geometry in self.geometries:
            shapely.prepare(geometry)

    def assign(self, geometry):
        matches = []
        for index in self.tree.query(geometry):
            boundary = self.geometries[int(index)]
            if boundary.covers(geometry):
                amount = geometry.area if geometry.area > 0 else geometry.length
            else:
                intersection = boundary.intersection(geometry)
                amount = intersection.area if geometry.area > 0 else intersection.length
            if amount > 0:
                matches.append((amount, self.entries[int(index)]['id']))
        if not matches:
            return None, []
        # 소속만 결정하며 원 형상·면적과 구를 넘는 유입 경계는 절단하지 않는다.
        matches.sort(key=lambda value: (-value[0], value[1]))
        return matches[0][1], [{'districtId': code, 'intersectionMeasure': value} for value, code in matches]


def prepare_database(connection):
    connection.executescript('''
        PRAGMA foreign_keys=ON;
        PRAGMA page_size=4096;
        PRAGMA cache_size=-65536;
        PRAGMA user_version=1;
        CREATE TABLE objects(object_id TEXT PRIMARY KEY,layer TEXT NOT NULL,role TEXT NOT NULL,
            representative_fid INTEGER NOT NULL,geometry_wkb BLOB NOT NULL,area_m2 REAL,length_m REAL,
            district_id TEXT NOT NULL,district_intersections TEXT NOT NULL,
            attribute_status TEXT NOT NULL DEFAULT 'CONSISTENT',
            overlap_count INTEGER NOT NULL DEFAULT 0,source_count INTEGER NOT NULL DEFAULT 1)
            WITHOUT ROWID;
        CREATE TABLE source_links(fid INTEGER PRIMARY KEY,object_id TEXT NOT NULL REFERENCES objects(object_id),
            tile TEXT NOT NULL,record_number INTEGER NOT NULL,raw_shape_sha256 TEXT NOT NULL,raw_dbf_sha256 TEXT NOT NULL);
        CREATE TABLE attribute_variants(object_id TEXT NOT NULL REFERENCES objects(object_id),sha256 TEXT NOT NULL,
            properties TEXT NOT NULL,PRIMARY KEY(object_id,sha256)) WITHOUT ROWID;
        CREATE INDEX source_links_object ON source_links(object_id);
        CREATE INDEX object_district ON objects(district_id,role);
    ''')


def build(catalog, boundaries, output, progress=None):
    if os.path.lexists(output) or output.parent.resolve() != output.parent.absolute():
        raise source.TopographyDataError('기존 객체 출력·출력 링크 덮어쓰기 금지')
    assignments = DistrictAssignment(boundaries)
    code_paths = {'generatorSha256': Path(__file__), 'decoderSha256': Path(native.__file__)}
    code_hashes = {key: spatial.file_sha256(path) for key, path in code_paths.items()}
    boundary_sha256 = source.digest(source.canonical(boundaries).encode())
    output.mkdir(mode=0o700)
    counts, role_counts, district_counts = Counter(), {}, Counter()
    try:
        with closing(sqlite3.connect('file:' + quote(str(catalog.database)) + '?mode=ro&immutable=1', uri=True)) as original:
            original.execute('PRAGMA trusted_schema=OFF')
            with closing(sqlite3.connect(output / 'objects.sqlite')) as target:
                prepare_database(target)
                for role in ROLES:
                    current = Counter()
                    sql = '''SELECT f.fid,f.tile,f.layer,f.record_number,f.raw_shape_sha256,f.raw_dbf_sha256,
                        f.geometry_wkb,f.properties,f.area_m2,f.length_m FROM layers l CROSS JOIN features f
                        ON f.tile=l.tile AND f.layer=l.layer WHERE l.role=? AND l.scale_denominator=1000
                        AND f.geometry_status='VALID' AND f.deleted=0 ORDER BY f.tile,f.layer,f.record_number'''
                    for fid, tile, layer, number, shape_sha, dbf_sha, wkb, props, area, length in original.execute(sql, (role,)):
                        geometry = shapely.from_wkb(wkb)
                        district, intersections = assignments.assign(geometry)
                        current['sourceRecords'] += 1
                        if district is None:
                            current['outsideCityRecords'] += 1
                            continue
                        identifier = object_key(layer, geometry)
                        previous = target.execute('SELECT representative_fid FROM objects WHERE object_id=?', (identifier,)).fetchone()
                        if previous is None:
                            target.execute('''INSERT INTO objects(object_id,layer,role,representative_fid,geometry_wkb,
                                area_m2,length_m,district_id,district_intersections) VALUES(?,?,?,?,?,?,?,?,?)''',
                                (identifier, layer, role, fid, wkb, area, length, district, source.canonical(intersections)))
                            current['objects'] += 1
                            district_counts[district + ':' + role] += 1
                        else:
                            existing = target.execute('SELECT geometry_wkb FROM objects WHERE object_id=?', (identifier,)).fetchone()[0]
                            if not shapely.equals_exact(shapely.from_wkb(existing), geometry, tolerance=0, normalize=True):
                                raise source.TopographyDataError('공간 객체 키 충돌')
                            target.execute('UPDATE objects SET source_count=source_count+1 WHERE object_id=?', (identifier,))
                            current['coincidentSourceRecords'] += 1
                        target.execute('INSERT INTO source_links VALUES(?,?,?,?,?,?)',
                            (fid, identifier, tile, number, shape_sha, dbf_sha))
                        properties = json.loads(props)
                        properties.pop('UFID', None)
                        comparable = source.canonical(properties)
                        target.execute('INSERT OR IGNORE INTO attribute_variants VALUES(?,?,?)',
                            (identifier, source.digest(comparable.encode()), comparable))
                    role_counts[role] = dict(sorted(current.items()))
                    counts.update(current)
                    if progress:
                        progress(role, dict(current))
                target.execute('''UPDATE objects SET attribute_status='CONFLICT' WHERE object_id IN
                    (SELECT object_id FROM attribute_variants GROUP BY object_id HAVING COUNT(*)>1)''')
                building_rows = target.execute("SELECT object_id,geometry_wkb FROM objects WHERE role='BUILDING_FOOTPRINT' ORDER BY object_id").fetchall()
                geometries = [shapely.from_wkb(row[1]) for row in building_rows]
                tree = STRtree(geometries)
                updates, overlaps = [], 0
                for index, geometry in enumerate(geometries):
                    count = 0
                    for other in tree.query(geometry, predicate='intersects'):
                        if int(other) == index:
                            continue
                        if geometry.intersection(geometries[int(other)]).area > 0:
                            count += 1
                    if count:
                        updates.append((count, building_rows[index][0]))
                        overlaps += count
                target.executemany('UPDATE objects SET overlap_count=? WHERE object_id=?', updates)
                counts['buildingOverlapPairs'] = overlaps // 2
                counts['buildingObjectsWithOverlap'] = len(updates)
                counts['attributeConflicts'] = target.execute("SELECT COUNT(*) FROM objects WHERE attribute_status='CONFLICT'").fetchone()[0]
                target.commit()
                target.execute('ANALYZE')
                target.execute('VACUUM')
                if target.execute('PRAGMA integrity_check').fetchone() != ('ok',) or target.execute('PRAGMA foreign_key_check').fetchone():
                    raise source.TopographyDataError('공간 객체 무결성·원본 대응 오류')
        if any(spatial.file_sha256(path) != code_hashes[key] for key, path in code_paths.items()):
            raise source.TopographyDataError('객체 생성 중 코드 변경')
        if spatial.file_sha256(catalog.database) != catalog.summary['spatialSha256']:
            raise source.TopographyDataError('객체 생성 중 공간 입력 변경')
        report = {'schemaVersion': 1, 'status': 'AUDITED_GEOMETRY_GROUPS_NOT_SERVICE_MIGRATED',
            'sourceSpatialSha256': catalog.summary['spatialSha256'], 'boundaryContentSha256': boundary_sha256,
            **code_hashes, 'objectsSha256': spatial.file_sha256(output / 'objects.sqlite'),
            'objectsBytes': (output / 'objects.sqlite').stat().st_size, 'counts': dict(sorted(counts.items())),
            'roleCounts': role_counts, 'districtRoleCounts': dict(sorted(district_counts.items())),
            'policy': {'exactCoincidenceOnly': True, 'coincidentIsAssetIdentity': False,
                'attributeConflictsArePlacementEligible': False, 'overlappingBuildingsArePlacementEligible': False,
                'ufidOnlyMerging': False, 'fragmentJoining': False, 'geometryRepair': False,
                'clipsGeometryToDistrict': False, 'sourceScaleDenominator': 1000, 'otherScalesRetainedInSource': True,
                'districtAssignment': 'LARGEST_POSITIVE_INTERSECTION_THEN_PUBLIC_CODE', 'serviceMigrated': False},
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
        expected = native.read_json(source.ROOT / 'data/manifests/seoul-spatial-catalog-v1.json')
        catalog = native.SpatialCatalog(source.ROOT / 'data/private/vworld-seoul-topography-20260307/spatial-v1', expected)
        boundaries = native.read_json(BOUNDARIES, limit=4 * 1024**2)
        report = build(catalog, boundaries, args.output.absolute(), progress=lambda role, count:
                       print(source.canonical({'role': role, 'counts': count}), flush=True))
    except source.TopographyDataError as exc:
        parser.exit(1, f'공간 객체 생성 실패: {exc}\n')
    except (OSError, ValueError, KeyError, TypeError, sqlite3.DatabaseError, shapely.errors.ShapelyError):
        parser.exit(1, '공간 객체 생성 실패: 입력·경계·도형 확인 필요\n')
    print(source.canonical({'counts': report['counts'], 'objectsSha256': report['objectsSha256']}))


if __name__ == '__main__':
    main()
