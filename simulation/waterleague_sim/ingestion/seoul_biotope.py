"""서울 도시생태현황도의 블록 면적 구성. 원값·모순·조사 한계 보존."""
from collections import Counter
from copy import deepcopy
import math

from waterleague_sim.engine.flood_errors import require
from waterleague_sim.terrain.grid import digest, finite

FIELDS = {'building': '건폐율', 'imperviousPaving': '불투포장율',
          'permeablePaving': '투수포장율', 'vegetation': '녹지율', 'bare': '기타비율'}
LEGENDS = {'10%미만': (0, 10), '10%이상~30%미만': (10, 30), '30%이상~50%미만': (30, 50),
           '50%이상~70%미만': (50, 70), '70%이상~90%미만': (70, 90), '90%이상': (90, 101)}
TOLERANCE_PERCENT = 1e-7


def composition(properties):
    require(isinstance(properties, dict), 'BIOTOPE_PROPERTIES_INVALID')
    raw = {key: properties.get(key) for key in (*FIELDS.values(), '불투토포비', '포장범례', '토지이용')}
    numbers = {key: raw[key] for key in (*FIELDS.values(), '불투토포비')}
    issues, warnings = [], []
    if any(not finite(v) for v in numbers.values()):
        issues.append('MISSING_OR_NONNUMERIC_PERCENT')
    elif any(not 0 <= v <= 100 for v in numbers.values()):
        issues.append('PERCENT_OUT_OF_RANGE')
    total_residual, sealed_residual = None, None
    if not issues:
        total_residual = math.fsum(raw[name] for name in FIELDS.values()) - 100
        sealed_residual = raw['건폐율'] + raw['불투포장율'] - raw['불투토포비']
        if abs(total_residual) > TOLERANCE_PERCENT:
            issues.append('COMPONENT_TOTAL_MISMATCH')
        if abs(sealed_residual) > TOLERANCE_PERCENT:
            issues.append('REPORTED_IMPERVIOUS_MISMATCH')
        legend = LEGENDS.get(raw['포장범례'])
        if legend is None or not legend[0] <= raw['불투토포비'] < legend[1]:
            warnings.append('LEGEND_DIFFERS_FROM_REPORTED_FRACTION')
    limitations = ['블록 단위 조사/영상 속성이며 포장 위치의 정밀 측량값 아님',
        '일부 투수포장 면적이 불투수 면적으로 산정될 가능성: 2025 보고서 264쪽 주석 66',
        '기타비율은 건설현장 등 나지를 포함하며 원지반 투수성의 확인값 아님']
    requirements = ['SOIL_PARAMETERS_AND_INITIAL_STATE', 'BLOCK_UNIFORM_ALLOCATION_ASSUMPTION']
    if finite(raw['투수포장율']) and raw['투수포장율'] > 0:
        requirements.append('PERMEABLE_PAVEMENT_LAYER_PARAMETERS')
    if raw['토지이용'] in ('J1', 'J2', 'J3', 'I2'):
        requirements.append('WATER_BODY_OR_WETLAND_HYDRAULICS')
    if raw['토지이용'] in ('H1', 'H2'):
        requirements.append('RESTRICTED_SURVEY_AREA_EVIDENCE')
    return {'status': 'CONSISTENT_REPORTED_COMPOSITION' if not issues else 'UNRESOLVED_SOURCE_VALUES',
        'raw': raw, 'issues': issues, 'warnings': warnings,
        'componentFractions': {key: raw[name] / 100 for key, name in FIELDS.items()} if not issues else None,
        'reportedImperviousFraction': raw['불투토포비'] / 100 if not issues else None,
        'componentTotalResidualPercent': total_residual, 'imperviousResidualPercent': sealed_residual,
        'sourceTolerancePercent': TOLERANCE_PERCENT, 'physicsRequirements': requirements,
        'limitations': limitations}


def normalize(features, edition_year):
    require(edition_year in (2010, 2020, 2025) and isinstance(features, list)
            and 0 < len(features) <= 100_000, 'BIOTOPE_INPUT_INVALID')
    records, original_ids, issues, warnings = [], Counter(), Counter(), Counter()
    for index, feature in enumerate(features):
        p = feature.get('properties')
        require(isinstance(p, dict) and isinstance(p.get('고유번호'), str)
                and p['고유번호'].strip(), 'BIOTOPE_SOURCE_ID_REQUIRED')
        original_ids[p['고유번호']] += 1
        value = composition(p)
        issues.update(value['issues']); warnings.update(value['warnings'])
        records.append({'id': f'SEOUL_BIOTOPE_{edition_year}:{index}', 'geometry': deepcopy(feature['geometry']),
            'properties': {'sourceRow': index, 'originalId': p['고유번호'], 'editionYear': edition_year,
                'landUse': p.get('토지이용'), 'district': p.get('자치구'), 'roofType': p.get('지붕유형'),
                'originalPropertiesSha256': digest(p), 'composition': value,
                'fieldInterpretation': '2025_REPORT_SCHEMA_SHARED_FIELD_NAMES_NOT_SHARED_SURVEY_DATE',
                'validFrom': None, 'validTo': None, 'surveyDate': None}})
    summary = {'editionYear': edition_year, 'features': len(records),
        'consistentRecords': sum(r['properties']['composition']['status'] == 'CONSISTENT_REPORTED_COMPOSITION'
                                 for r in records), 'duplicateOriginalIds': sum(v-1 for v in original_ids.values()),
        'issues': dict(sorted(issues.items())), 'warnings': dict(sorted(warnings.items())),
        'classification': 'PUBLIC_BLOCK_SURVEY_COMPOSITION_NOT_POINT_MEASUREMENT', 'rankingEligible': False}
    return records, summary


def soil_cover_parameters(records, *, allocation_evidence):
    """포장층·수면 등 추가 모형이 필요 없는 블록만 명시적 토양 배정 후보 생성."""
    require(isinstance(allocation_evidence, str) and allocation_evidence.strip(),
            'BIOTOPE_ALLOCATION_EVIDENCE_REQUIRED')
    result, unresolved = {}, {}
    for row in records:
        value = row['properties']['composition']
        reasons = list(value['issues']) + [r for r in value['physicsRequirements'] if r not in
            ('SOIL_PARAMETERS_AND_INITIAL_STATE', 'BLOCK_UNIFORM_ALLOCATION_ASSUMPTION')]
        if reasons:
            unresolved[row['id']] = reasons
            continue
        fractions = value['componentFractions']
        result[row['id']] = {'perviousFraction': fractions['vegetation'] + fractions['bare'],
            'evidence': {'source': deepcopy(row['properties']), 'allocation': allocation_evidence,
                'interpretation': 'REPORTED_GREEN_AND_BARE_AREA_AS_SOIL_SCENARIO_NOT_MEASURED_HYDRAULICS'}}
    return result, unresolved
