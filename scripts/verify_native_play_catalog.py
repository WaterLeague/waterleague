"""전체 게임 자료의 원형·분류·공통 조건과 실제 EPA 연결 대조."""
import argparse
from collections import Counter
from contextlib import closing
from decimal import Decimal
import json
import math
import os
from pathlib import Path
import sqlite3
import inspect
from urllib.parse import quote

import shapely

import prepare_native_play_catalog as producer
import prepare_seoul_spatial as spatial
import prepare_seoul_topography as source
import topography_catalog as native
from waterleague_sim.engine import continuous, facilities
from waterleague_sim.spatial import design_footprint, reference_conditions
from waterleague_sim.spatial.geometry import cell_geometry, dimensions
from waterleague_sim.spatial.play_catalog import NativePlayCatalog

FORCING = source.ROOT / 'data/models/seongsu-421-20240718.json'
FORCING_SHA256 = 'fff031781cebc7f1b1f8e6cd0ed284c2166f688d80a2c70a2e4c24ee2df438c3'


def expected_surface(kind, role, properties):
    if kind == 'ROOF' and role == 'BUILDING_FOOTPRINT':
        return 'ROOF_REFERENCE', ['GREEN_ROOF']
    if kind == 'GROUND' and role in ('ROAD_AREA', 'SIDEWALK_AREA'):
        return 'PAVEMENT_REFERENCE', ['PERMEABLE_PAVEMENT']
    if kind == 'GROUND' and role == 'CULTIVATION_LANDSCAPE_AREA':
        if properties.get('구분') == '밭':
            return 'DRY_CULTIVATION_REFERENCE', ['RAIN_GARDEN', 'BIORETENTION']
        if properties.get('구분') in ('과수원', '목초지'):
            return 'GRASS_REFERENCE', ['RAIN_GARDEN', 'BIORETENTION']
    return None, []


def verify(directory, site_directory, object_directory, *, progress=None):
    summary = native.read_json(directory / 'summary.json')
    reader = NativePlayCatalog(directory / 'play.sqlite', summary['playSha256'])
    settings = reader.metadata()
    expected = producer.metadata(native.read_json(site_directory / 'summary.json'),
                                 native.read_json(object_directory / 'summary.json'))
    if settings != expected:
        raise source.TopographyDataError('게임 자료의 공통 조건·단가·정책 불일치')
    paths = [(directory / 'play.sqlite', summary['playSha256']),
        (site_directory / 'sites.sqlite', summary['sourceSitesSha256']),
        (object_directory / 'objects.sqlite', summary['sourceObjectsSha256'])]
    for path, checksum in paths[1:]:
        with source.source_stream(path, expected_sha256=checksum, limit=16 * 1024**3):
            pass
    code_paths = [Path(__file__), Path(producer.__file__), Path(inspect.getfile(NativePlayCatalog))]
    code_paths += [Path(module.__file__) for module in (
        producer.playing_profile, reference_conditions, producer.geometry_code, design_footprint, facilities)]
    checksums = {str(path): spatial.file_sha256(path) for path in code_paths}
    counts, facility_counts, districts, surfaces = Counter(), Counter(), Counter(), Counter()
    with closing(reader.connection()) as database:
        database.execute('ATTACH DATABASE ? AS shapes', ('file:' + quote(str(site_directory / 'sites.sqlite')) + '?mode=ro&immutable=1',))
        database.execute('ATTACH DATABASE ? AS originals', ('file:' + quote(str(object_directory / 'objects.sqlite')) + '?mode=ro&immutable=1',))
        if database.execute('PRAGMA integrity_check').fetchone() != ('ok',):
            raise source.TopographyDataError('게임 자료 무결성 대조 실패')
        original_count = database.execute('SELECT COUNT(*) FROM shapes.candidates').fetchone()[0]
        if database.execute('SELECT COUNT(*) FROM sites').fetchone()[0] != original_count:
            raise source.TopographyDataError('게임 자료 후보 누락')
        rows = database.execute('''SELECT p.id,p.object_id,p.district_id,p.kind,p.role,p.status,p.allowed_mask,p.cx,p.cy,p.body,
            c.geometry_wkb,c.geometry_sha256,c.area_m2,c.max_area_m2,c.object_id,c.district_id,c.kind,c.role,
            (SELECT properties FROM originals.attribute_variants v WHERE v.object_id=c.object_id ORDER BY sha256 LIMIT 1)
            FROM sites p JOIN shapes.candidates c ON c.id=p.id ORDER BY p.fid''')
        for index, row in enumerate(rows, 1):
            (identifier, object_id, district, kind, role, status, mask, cx, cy, body, raw, geometry_sha,
             area, limit, parent, original_district, original_kind, original_role, attributes) = row
            cell, properties = json.loads(body), json.loads(attributes)
            geometry = cell_geometry(cell)
            if (shapely.to_wkb(geometry) != raw or cell['geometrySha256'] != geometry_sha
                    or (object_id, district, kind, role) != (parent, original_district, original_kind, original_role)
                    or any(cell[key] != value for key, value in (
                        ('id', identifier), ('districtId', district), ('kind', kind), ('role', role),
                        ('sourceObjectId', parent), ('areaM2', area), ('maxAreaM2', float(limit)),
                        ('sourceIds', [parent]), ('geometryCrs', 'EPSG:5186'), ('status', status)))
                    or Decimal(str(cell['maxAreaM2'])) != Decimal(limit)
                    or cell['sourceLandUse'] != properties.get('구분')
                    or cell['constructionEligibility'] != 'UNKNOWN'):
                raise source.TopographyDataError('게임 자료의 원형·면적·속성·소속 결속 불일치')
            center = geometry.representative_point()
            if [cx, cy] != cell['centerProjected'] or [cx, cy] != [center.x, center.y]:
                raise source.TopographyDataError('게임 자료 선택 중심 불일치')
            scenario, allowed = expected_surface(kind, role, properties)
            if scenario is None:
                if status != 'UNSUPPORTED_SURFACE_PROCESS' or cell['allowedTypes'] or mask or 'physicalInputs' in cell:
                    raise source.TopographyDataError('미지원 표면을 계산 가능 후보로 변환')
            else:
                reference_conditions.validate(cell)
                physical = cell['physicalInputs']
                if (physical['surfaceScenarioId'] != scenario or status != 'EXPLORATORY_REFERENCE_SCENARIO'
                        or any(physical[key] != 'UNRESOLVED' for key in ('localSoilStatus', 'localSlopeStatus', 'localMaterialStatus'))
                        or physical['geometrySourceIds'] != [parent]
                        or cell['inflowPolicy'] != 'DIRECT_RAINFALL_ONLY' or cell['siteEligibility'] != 'UNKNOWN'
                        or any(physical[key] != value for key, value in dimensions(geometry).items())):
                    raise source.TopographyDataError('게임 자료의 계산 조건·현장 결측 구분 실패')
                for key, facility in (('swaleDesign', 'VEGETATIVE_SWALE'), ('trenchDesign', 'INFILTRATION_TRENCH')):
                    if key in physical:
                        if 'RAIN_GARDEN' not in allowed:
                            raise source.TopographyDataError('고정 폭 시설의 표면 분류 불일치')
                        design_footprint.validate(cell, physical[key])
                        (facilities.swale_design if facility == 'VEGETATIVE_SWALE' else facilities.trench_design)(cell)
                        allowed.append(facility)
                if cell['allowedTypes'] != allowed:
                    raise source.TopographyDataError('표면 분류와 시설 허용 목록 불일치')
                if 'RAIN_GARDEN' in allowed:
                    for key, boundary in (
                        ('rainGardenBoundary', facilities.native_soil_boundary(cell, settings['hydrology'])),
                        ('bioretentionBoundary', facilities.bioretention_boundary(cell))):
                        if physical[key] != boundary:
                            raise source.TopographyDataError('원지반 경계의 문헌 조건 불일치')
                if 'INFILTRATION_TRENCH' in allowed and physical['trenchBoundary'] != facilities.trench_boundary(cell):
                    raise source.TopographyDataError('침투도랑 원지반 경계 불일치')
                surfaces[scenario] += 1
            if mask != sum(1 << producer.playing_profile.FACILITY_ORDER.index(key) for key in allowed):
                raise source.TopographyDataError('설치 허용 인덱스 불일치')
            counts['records'] += 1
            counts[status] += 1
            districts[district + ':' + kind] += 1
            facility_counts.update(allowed)
            if progress and index % 100_000 == 0:
                progress(index)
        if (counts['records'] != original_count or dict(counts) != summary['counts']
                or dict(districts) != summary['districtKindCounts'] or dict(facility_counts) != summary['facilityCounts']):
            raise source.TopographyDataError('게임 자료 전체 집계 불일치')
    if (any(spatial.file_sha256(path) != checksum for path, checksum in paths)
            or any(spatial.file_sha256(path) != checksum for path, checksum in checksums.items())):
        raise source.TopographyDataError('게임 자료 대조 중 입력·코드 변경')
    return {'schemaVersion': 1, 'status': 'PASS', 'verifierSha256': checksums[str(Path(__file__))],
        'readerSha256': checksums[str(code_paths[2])], 'playSha256': summary['playSha256'],
        'counts': dict(counts), 'districtCount': len({key.split(':')[0] for key in districts}),
        'surfaceCounts': dict(sorted(surfaces.items())), 'facilityCounts': dict(facility_counts),
        'sourceGeometryWkbByteIdentical': True, 'localSoilSlopeMaterialConfirmed': False,
        'constructionApproved': False, 'serviceMigrated': False}


def engine_cases(directory, output):
    if os.path.lexists(output):
        raise source.TopographyDataError('기존 실제 시설 대조 덮어쓰기 금지')
    report = native.read_json(directory / 'summary.json')
    reader = NativePlayCatalog(directory / 'play.sqlite', report['playSha256'])
    with source.source_stream(FORCING, expected_sha256=FORCING_SHA256) as (stream, _):
        forcing = json.load(stream)['rainfall']
    output.mkdir(mode=0o700)
    results = []
    for index, facility in enumerate(producer.playing_profile.FACILITY_ORDER):
        with closing(reader.connection()) as database:
            row = database.execute('''SELECT id,district_id FROM sites WHERE allowed_mask & ? <> 0
                AND json_extract(body,'$.areaM2') BETWEEN 25 AND 1000 ORDER BY fid LIMIT 1''', (1 << index,)).fetchone()
        if row is None:
            raise source.TopographyDataError('공개 원형 시설 대조 사례 누락')
        identifier, district = row
        model = reader.model(identifier, district=district)
        model['rainfall'] = forcing
        cell = model['cells'][0]
        maximum = cell['maxAreaM2']
        if facility in ('VEGETATIVE_SWALE', 'INFILTRATION_TRENCH'):
            maximum = cell['physicalInputs']['swaleDesign' if facility == 'VEGETATIVE_SWALE' else 'trenchDesign']['maxAreaM2']
        placement = reader.placement(identifier, facility, maximum, district=district)
        result = continuous.experiment(model, placement, output / facility.lower())
        expected = maximum * math.fsum(forcing['depthsMm']) / 1000
        if not math.isclose(result['strategy']['final']['lidInflowM3'], expected, abs_tol=1e-5, rel_tol=1e-6):
            raise source.TopographyDataError('시설 직접 강우 체적 불일치')
        results.append({'facilityType': facility, 'candidateId': identifier, 'districtId': district,
            'geometrySha256': cell['geometrySha256'], 'areaM2': maximum, 'costKrw': placement['costKrw'],
            'directRainVolumeMatched': True, 'engine': result['strategy']['engine'],
            'resultSha256': spatial.file_sha256(output / facility.lower() / 'result.json')})
    return {'forcingSourceSha256': FORCING_SHA256, 'forcingUse': 'COMMON_OBSERVED_REPLAY_NOT_LOCAL_OBSERVATION',
        'antecedentSpinupApplied': False, 'initialStateUse': 'DECLARED_SEED_ENGINE_LINK_CHECK_NOT_EVENT_EVALUATION',
        'rankingEligible': False, 'cases': results}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--play', type=Path, default=producer.OUTPUT)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--engine-output', type=Path)
    args = parser.parse_args()
    try:
        if os.path.lexists(args.output):
            raise source.TopographyDataError('기존 시설 자료 대조 기록 덮어쓰기 금지')
        report = verify(args.play, producer.sites.OUTPUT, producer.sites.ROOT / 'objects-v1',
                        progress=lambda done: print(f'시설 자료 전체 대조 {done}', flush=True))
        if args.engine_output is not None:
            report['engineValidation'] = engine_cases(args.play, args.engine_output)
        with args.output.open('x', encoding='utf-8') as stream:
            stream.write(source.canonical(report) + '\n')
    except (OSError, ValueError, KeyError, TypeError, sqlite3.DatabaseError, shapely.errors.ShapelyError):
        parser.exit(1, '시설 자료 대조 실패: 원형·공통 조건·계산 연결 확인 필요\n')
    print(source.canonical({'status': report['status'], 'records': report['counts']['records']}))


if __name__ == '__main__':
    main()
