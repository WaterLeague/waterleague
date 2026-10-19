"""원형·시설 조건·공개 단가를 함께 읽는 불변 게임 자료 생성."""
import argparse
from collections import Counter
from contextlib import closing
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
from urllib.parse import quote

import shapely
from shapely.geometry import mapping

import prepare_seoul_spatial as spatial
import prepare_seoul_topography as source
import prepare_topography_sites as sites
import topography_catalog as native

sys.path.insert(0, str(source.ROOT / 'simulation'))
from waterleague_sim.engine import facilities, initialization
from waterleague_sim.spatial import playing_profile, reference_conditions, geometry as geometry_code, design_footprint

OUTPUT = sites.ROOT / 'play-v1'
COST_PATH = source.ROOT / 'data/costs/lid-reference-v5.json'
COST_SHA256 = '50f6e00757ecba3ed77a811b0fd9d03f72b800c0c47712093bf1adda99421036'
BUDGET_PATH = source.ROOT / 'backend/src/main/resources/budget/seoul-2026.json'


def connect(path):
    value = sqlite3.connect('file:' + quote(str(path)) + '?mode=ro&immutable=1', uri=True)
    value.execute('PRAGMA trusted_schema=OFF')
    return value


def metadata(site_summary, object_summary):
    with source.source_stream(COST_PATH, expected_sha256=COST_SHA256) as (stream, _):
        costs = json.load(stream)
    with source.source_stream(BUDGET_PATH) as (stream, budget_sha):
        budget = json.load(stream)
    with source.source_stream(facilities.CATALOG_V4_PATH, expected_sha256=facilities.CATALOG_V4_SHA256):
        pass
    return {'schemaVersion': 1, 'id': 'SEOUL_NGII_REFERENCE_PLAY_V1', 'coordinateSystem': 'EPSG:5186',
        'originProjected': [198128, 551989], 'distributionUpdatedAt': '2026-03-07',
        'sourceSitesSha256': site_summary['sitesSha256'], 'sourceObjectsSha256': object_summary['objectsSha256'],
        'sourceSpatialSha256': site_summary['sourceSpatialSha256'],
        'referenceScenario': reference_conditions.reference(), 'referenceConditions': reference_conditions.catalog(),
        'facilityDesignSet': facilities.design_set(4), 'costModel': costs, 'costSourceSha256': COST_SHA256,
        'unitCosts': {key: value['unitCost'] for key, value in costs['facilities'].items()},
        'budgetPolicy': budget, 'budgetPolicySha256': budget_sha, 'budget': budget['personalLimitKrw'],
        'hydrology': playing_profile.hydrology(),
        'initializationPolicy': {'method': initialization.METHOD, 'warmupMinutes': initialization.MINUTES},
        'policy': {'constructionEligibility': 'UNKNOWN', 'fieldSoilInferred': False, 'fieldSlopeInferred': False,
            'externalInflowConnected': False, 'currentGeometryAppliedToHistoricalEvents': True,
            'facilityAndCostBindingComplete': True, 'serviceMigrated': False},
        'attribution': '국토지리정보원 수치지도V2.0 · 브이월드 · 서울특별시/서울신용보증재단 자치구 영역 · US EPA 공개 문헌',
        'limitations': ['실제 형상과 공통 문헌 토양·표면 설계 조건의 독립 표면 비교',
            '토성·경사·포장재·하중·방수/배수·지하수·지장물 현장 미확인',
            '자료 갱신일은 조사·촬영·과거 자산 존재 시점과 다름',
            '설치비는 공개 참고 단가의 포함/제외 범위를 따르며 전체 발주금액·LCC 아님',
            '관망·외부 집수 연결 없이 시설 자체 강우만 처리; 실제 도시 침수 예측 아님']}


def prepare_database(database):
    database.executescript('''PRAGMA page_size=4096;PRAGMA cache_size=-65536;PRAGMA user_version=1;
        CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL) WITHOUT ROWID;
        CREATE TABLE sites(fid INTEGER PRIMARY KEY,id TEXT UNIQUE NOT NULL,object_id TEXT UNIQUE NOT NULL,
            district_id TEXT NOT NULL,kind TEXT NOT NULL,role TEXT NOT NULL,status TEXT NOT NULL,
            allowed_mask INTEGER NOT NULL,cx REAL NOT NULL,cy REAL NOT NULL,body TEXT NOT NULL);
        CREATE VIRTUAL TABLE site_bounds USING rtree(fid,minx,maxx,miny,maxy);
        CREATE INDEX sites_district_kind ON sites(district_id,kind,allowed_mask);
    ''')


def build(site_directory, object_directory, output, progress=None):
    if os.path.lexists(output) or output.parent.resolve() != output.parent.absolute():
        raise source.TopographyDataError('기존 게임 자료·출력 링크 덮어쓰기 금지')
    site_summary, object_summary = native.read_json(site_directory / 'summary.json'), native.read_json(object_directory / 'summary.json')
    if site_summary['sourceObjectsSha256'] != object_summary['objectsSha256']:
        raise source.TopographyDataError('게임 형상·원 객체 버전 불일치')
    site_db, object_db = site_directory / 'sites.sqlite', object_directory / 'objects.sqlite'
    for path, checksum in [(site_db, site_summary['sitesSha256']), (object_db, object_summary['objectsSha256'])]:
        with source.source_stream(path, expected_sha256=checksum, limit=16 * 1024**3):
            pass
    settings = metadata(site_summary, object_summary)
    modules = {'generatorSha256': Path(__file__), 'profileCodeSha256': Path(playing_profile.__file__),
        'referenceCodeSha256': Path(reference_conditions.__file__), 'geometryCodeSha256': Path(geometry_code.__file__),
        'footprintCodeSha256': Path(design_footprint.__file__), 'facilityCodeSha256': Path(facilities.__file__),
        'initializationCodeSha256': Path(initialization.__file__)}
    checksums = {key: spatial.file_sha256(path) for key, path in modules.items()}
    output.mkdir(mode=0o700)
    counts, district_counts, facility_counts = Counter(), Counter(), Counter()
    try:
        with closing(connect(site_db)) as original, closing(sqlite3.connect(output / 'play.sqlite')) as target:
            original.execute('ATTACH DATABASE ? AS originals', ('file:' + quote(str(object_db)) + '?mode=ro&immutable=1',))
            prepare_database(target)
            target.execute('INSERT INTO metadata VALUES(?,?)', ('catalog', source.canonical(settings)))
            rows = original.execute('''SELECT c.id,c.object_id,c.district_id,c.kind,c.role,c.geometry_wkb,
                c.geometry_sha256,c.area_m2,c.max_area_m2,v.properties FROM candidates c
                JOIN originals.attribute_variants v ON v.object_id=c.object_id
                WHERE v.sha256=(SELECT MIN(sha256) FROM originals.attribute_variants WHERE object_id=c.object_id)
                ORDER BY c.id''')
            for identifier, object_id, district, kind, role, raw, geometry_sha, area, limit, attributes in rows:
                shape = shapely.from_wkb(raw)
                cell = {'id': identifier, 'sourceObjectId': object_id, 'districtId': district, 'kind': kind, 'role': role,
                    'geometry': mapping(shape), 'geometryCrs': 'EPSG:5186', 'geometrySha256': geometry_sha,
                    'areaM2': area, 'maxAreaM2': float(limit), 'sourceIds': [object_id]}
                profile = playing_profile.bind(cell, json.loads(attributes))
                center = shape.representative_point()
                cell.update(centerProjected=[center.x, center.y], heightM=.05, heightBasis='GROUND_DISPLAY_OFFSET',
                    siteEligibility='UNKNOWN', inflowPolicy='DIRECT_RAINFALL_ONLY')
                cell.update(profile)
                allowed = sum(1 << playing_profile.FACILITY_ORDER.index(key) for key in profile['allowedTypes'])
                cursor = target.execute('INSERT INTO sites(id,object_id,district_id,kind,role,status,allowed_mask,cx,cy,body) VALUES(?,?,?,?,?,?,?,?,?,?)',
                    (identifier, object_id, district, kind, role, profile['status'], allowed, center.x, center.y, source.canonical(cell)))
                a, b, c, d = shape.bounds
                target.execute('INSERT INTO site_bounds VALUES(?,?,?,?,?)', (cursor.lastrowid, a, c, b, d))
                counts['records'] += 1
                counts[profile['status']] += 1
                district_counts[district + ':' + kind] += 1
                facility_counts.update(profile['allowedTypes'])
                if progress and counts['records'] % 100_000 == 0:
                    progress(counts['records'])
            if counts['records'] != site_summary['counts']['CANDIDATE']:
                raise source.TopographyDataError('게임 자료의 설계 영역·속성 대응 누락')
            target.commit()
            target.execute('ANALYZE')
            target.execute('VACUUM')
            if target.execute('PRAGMA integrity_check').fetchone() != ('ok',):
                raise source.TopographyDataError('게임 자료 무결성 오류')
        for path, checksum in [(site_db, site_summary['sitesSha256']), (object_db, object_summary['objectsSha256']),
                               (COST_PATH, COST_SHA256), (BUDGET_PATH, settings['budgetPolicySha256']),
                               (reference_conditions.PATH, reference_conditions.SHA256)]:
            if spatial.file_sha256(path) != checksum:
                raise source.TopographyDataError('게임 자료 생성 중 원본·비교 조건 변경')
        if any(spatial.file_sha256(path) != checksums[key] for key, path in modules.items()):
            raise source.TopographyDataError('게임 자료 생성 중 코드 변경')
        report = {'schemaVersion': 1, 'status': 'BOUND_REFERENCE_PLAY_CATALOG_NOT_SERVICE_MIGRATED', **checksums,
            'playSha256': spatial.file_sha256(output / 'play.sqlite'), 'playBytes': (output / 'play.sqlite').stat().st_size,
            'sourceSitesSha256': site_summary['sitesSha256'], 'sourceObjectsSha256': object_summary['objectsSha256'],
            'referenceScenario': settings['referenceScenario'], 'facilityDesignSet': settings['facilityDesignSet'],
            'costSourceSha256': COST_SHA256, 'budgetPolicySha256': settings['budgetPolicySha256'],
            'counts': dict(sorted(counts.items())), 'districtKindCounts': dict(sorted(district_counts.items())),
            'facilityCounts': dict(sorted(facility_counts.items())), 'policy': settings['policy'],
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
        expected = native.read_json(source.ROOT / 'data/manifests/seoul-topography-sites-v1.json')
        actual = native.read_json(sites.OUTPUT / 'summary.json')
        if any(actual[key] != expected[key] for key in ('sitesSha256', 'sourceObjectsSha256', 'generatorSha256')):
            raise source.TopographyDataError('공개 설계 영역 요약 불일치')
        report = build(sites.OUTPUT, sites.ROOT / 'objects-v1', args.output.absolute(),
                       progress=lambda done: print(f'시설·단가 결속 {done}', flush=True))
    except source.TopographyDataError as exc:
        parser.exit(1, f'게임 자료 생성 실패: {exc}\n')
    except (OSError, ValueError, KeyError, TypeError, sqlite3.DatabaseError, shapely.errors.ShapelyError):
        parser.exit(1, '게임 자료 생성 실패: 원형·시설·단가 확인 필요\n')
    print(source.canonical({'playSha256': report['playSha256'], 'counts': report['counts'], 'facilityCounts': report['facilityCounts']}))


if __name__ == '__main__':
    main()
