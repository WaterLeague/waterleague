"""실제 원 도형과 보관 관측 강우의 독립 표면 SWMM 연결 대조."""
import argparse
import copy
from contextlib import closing
import json
import math
import os
from pathlib import Path
import shutil
import sqlite3

import shapely
from shapely.geometry import mapping

import prepare_seoul_spatial as spatial
import prepare_seoul_topography as source
import prepare_topography_sites as sites
import topography_catalog as native
from waterleague_sim.engine import continuous
from waterleague_sim.engine.facilities import design_set
from waterleague_sim.spatial.geometry import dimensions

FORCING = source.ROOT / 'data/models/seongsu-421-20240718.json'
FORCING_SHA256 = 'fff031781cebc7f1b1f8e6cd0ed284c2166f688d80a2c70a2e4c24ee2df438c3'


def selected_cases(directory):
    with closing(sites.connect(directory / 'sites.sqlite')) as database:
        result = []
        for kind, facility in [('ROOF', 'GREEN_ROOF'), ('GROUND', 'PERMEABLE_PAVEMENT')]:
            rows = database.execute('''SELECT id,object_id,district_id,geometry_wkb,area_m2,max_area_m2
                FROM candidates WHERE kind=? AND area_m2 BETWEEN 25 AND 5000
                AND (kind='ROOF' OR role IN ('ROAD_AREA','SIDEWALK_AREA')) ORDER BY id''', (kind,))
            for identifier, object_id, district, raw, area, limit in rows:
                geometry = shapely.from_wkb(raw)
                parts = [geometry] if geometry.geom_type == 'Polygon' else list(geometry.geoms)
                if kind == 'ROOF' and len(parts) == 1 and not parts[0].interiors:
                    continue
                if kind == 'GROUND' and len(parts) == 1 and not parts[0].interiors:
                    continue
                result.append({'id': identifier, 'objectId': object_id, 'districtId': district,
                    'kind': kind, 'geometry': mapping(geometry), 'geometryCrs': 'EPSG:5186',
                    'areaM2': area, 'maxAreaM2': float(limit),
                    'physicalInputs': dimensions(geometry) | {'slopePercent': 1},
                    'allowedTypes': [facility]})
                break
            else:
                raise source.TopographyDataError('복수 면·구멍을 가진 실제 도형 대조 사례 미확보')
        return result


def verify(directory, output):
    if os.path.lexists(output):
        raise source.TopographyDataError('기존 원 도형 엔진 대조 덮어쓰기 금지')
    summary = native.read_json(directory / 'summary.json')
    with source.source_stream(directory / 'sites.sqlite', expected_sha256=summary['sitesSha256'], limit=16 * 1024**3):
        pass
    with source.source_stream(FORCING, expected_sha256=FORCING_SHA256) as (stream, _):
        forcing = json.load(stream)
    cases = selected_cases(directory)
    code_sha = spatial.file_sha256(__file__)
    output.mkdir(mode=0o700)
    reports = []
    try:
        for cell in cases:
            kind = cell['kind'].lower()
            model = {'cells': [cell], 'hydrology': copy.deepcopy(forcing['hydrology']),
                'rainfall': copy.deepcopy(forcing['rainfall']), 'facilityDesignSet': design_set(4),
                'sharedSiteSource': {'inflowPolicy': 'DIRECT_RAINFALL_ONLY'},
                'geometrySource': {'sitesSha256': summary['sitesSha256'], 'sourceObjectId': cell['objectId']},
                'forcingUse': 'COMMON_OBSERVED_REPLAY_NOT_LOCAL_OBSERVATION',
                'hydrologyUse': 'REGISTERED_EXPLORATORY_DESIGN_NOT_LOCAL_OBSERVATIONS',
                'assumptions': ['실제 수치지형도 설계 영역과 보관 AWS 421 관측의 엔진 연결 시험',
                    '관측 강우는 해당 도형 위치의 현장 관측이 아닌 공통 재생 입력',
                    '수문 상수와 경사 1%는 기존 탐색 설계 조건이며 해당 현장 실측 아님',
                    '배수 연결 미확인으로 시설 자체 강우만 처리; 운영 모델·순위 미등록']}
            placement = {'cellId': cell['id'], 'facilityType': cell['allowedTypes'][0], 'areaM2': cell['maxAreaM2']}
            result = continuous.experiment(model, placement, output / kind)
            rain = math.fsum(model['rainfall']['depthsMm']) / 1000
            expected_rain = cell['areaM2'] * rain
            expected_lid = cell['maxAreaM2'] * rain
            for name in ('baseline', 'strategy'):
                actual = result[name]['final']['precipitationM3']
                if not math.isclose(actual, expected_rain, abs_tol=1e-5, rel_tol=1e-6):
                    raise source.TopographyDataError('실제 원 도형 강우 체적 불일치')
            if not math.isclose(result['strategy']['final']['lidInflowM3'], expected_lid, abs_tol=1e-5, rel_tol=1e-6):
                raise source.TopographyDataError('실제 원 도형 직접 강우 유입 경계 불일치')
            reports.append({'kind': cell['kind'], 'candidateId': cell['id'], 'sourceObjectId': cell['objectId'],
                'areaM2': cell['areaM2'], 'maximumAreaM2': cell['maxAreaM2'],
                'precipitationVolumeMatched': True, 'directRainLidInflowMatched': True,
                'runoffContinuityPercent': {name: result[name]['runoffContinuityPercent'] for name in ('baseline', 'strategy')},
                'engine': result['strategy']['engine'],
                'resultSha256': spatial.file_sha256(output / kind / 'result.json')})
        if spatial.file_sha256(__file__) != code_sha or spatial.file_sha256(directory / 'sites.sqlite') != summary['sitesSha256']:
            raise source.TopographyDataError('원 도형 엔진 대조 중 입력·코드 변경')
        report = {'schemaVersion': 1, 'status': 'PASS', 'verifierSha256': code_sha,
            'sitesSha256': summary['sitesSha256'], 'forcingSourceModelSha256': FORCING_SHA256,
            'forcingUse': 'COMMON_OBSERVED_REPLAY_NOT_LOCAL_OBSERVATION', 'cases': reports,
            'fieldValidated': False, 'connectedCatchmentValidated': False, 'rankingEligible': False, 'serviceMigrated': False}
        with (output / 'summary.json').open('x', encoding='utf-8') as stream:
            stream.write(source.canonical(report) + '\n')
        return report
    except BaseException:
        shutil.rmtree(output)
        raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--sites', type=Path, default=sites.OUTPUT)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = verify(args.sites, args.output)
    except source.TopographyDataError as exc:
        parser.exit(1, f'원 도형 엔진 대조 실패: {exc}\n')
    except (OSError, ValueError, KeyError, TypeError, sqlite3.DatabaseError, shapely.errors.ShapelyError):
        parser.exit(1, '원 도형 엔진 대조 실패: 원형·관측·엔진 확인 필요\n')
    print(source.canonical({'status': result['status'], 'cases': len(result['cases']), 'rankingEligible': False}))


if __name__ == '__main__':
    main()
