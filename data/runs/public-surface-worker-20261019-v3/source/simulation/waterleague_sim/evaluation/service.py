"""고정 비교 조건의 원 지표 변화량·효과별 점수·총점."""
from fractions import Fraction

from .exception import require
from .values import digest, encoded, is_hash, number

METRICS = {
    'outwardVolumeM3': ('m3', -1),
    'peakOutwardM3s': ('m3/s', -1),
    'depthAreaTimeM3Hours': ('m3*h', -1),
    'reusedVolumeM3': ('m3', 1),
    'removedPollutantKg': ('kg', 1),
}
BASE_METRICS = frozenset(list(METRICS)[:3])
CONTEXT_FIELDS = frozenset(('scopeId', 'modelGrade', 'evidenceClass', 'comparisonKind', 'effectAreaId',
    'scenarioSnapshotSha256', 'forcingSha256', 'engineSha256', 'metricSpecificationSha256'))


def validate_policy(policy):
    require(isinstance(policy, dict)
            and set(policy) == {'schemaVersion', 'policyVersion', 'context', 'metrics', 'requiredMetrics'}
            and type(policy.get('schemaVersion')) is int and policy['schemaVersion'] == 1
            and isinstance(policy.get('policyVersion'), str) and 0 < len(policy['policyVersion']) <= 100,
            'EFFECT_POLICY_INVALID')
    context = policy.get('context')
    require(isinstance(context, dict) and set(context) == CONTEXT_FIELDS
            and all(isinstance(v, str) and 0 < len(v) <= 200 for v in context.values())
            and all(is_hash(v) for k, v in context.items() if k.endswith('Sha256'))
            and context['modelGrade'] in ('DRAFT', 'EXPLORATORY', 'BENCHMARKED', 'SITE_VALIDATED')
            and context['evidenceClass'] in ('NUMERICAL_TEST_ONLY', 'PUBLIC_DATA')
            and (context['evidenceClass'] != 'NUMERICAL_TEST_ONLY' or context['modelGrade'] == 'DRAFT')
            and context['comparisonKind'] in ('CURRENT', 'HISTORICAL_RECONSTRUCTION', 'PAST_RAINFALL_STRESS_TEST'),
            'EFFECT_CONTEXT_INVALID')
    metrics = policy.get('metrics')
    require(isinstance(metrics, dict) and set(metrics) in (BASE_METRICS, frozenset(METRICS)),
            'EFFECT_METRICS_INVALID')
    required = policy.get('requiredMetrics')
    require(isinstance(required, list) and len(required) == len(metrics)
            and set(required) == set(metrics), 'EFFECT_REQUIRED_METRICS_INVALID')
    weights = []
    for key, row in metrics.items():
        require(isinstance(row, dict) and set(row) == {'unit', 'reference', 'weight', 'evidenceSha256'}
                and row.get('unit') == METRICS[key][0]
                and number(row.get('reference')) > 0, 'EFFECT_REFERENCE_INVALID')
        weight = number(row.get('weight'))
        require(0 <= weight <= 1, 'EFFECT_WEIGHT_INVALID')
        refs = row.get('evidenceSha256')
        require(isinstance(refs, list) and 1 <= len(refs) <= 32 and all(is_hash(v) for v in refs),
                'EFFECT_REFERENCE_EVIDENCE_REQUIRED')
        weights.append(weight)
    require(sum(weights) == 1, 'EFFECT_WEIGHTS_NOT_NORMALIZED')
    return digest(policy)


def validate_record(record, context):
    require(isinstance(record, dict) and set(record) == {'schemaVersion', 'context', 'inputSha256',
            'resultSha256', 'numericalStatus', 'complete', 'raw'}
            and type(record.get('schemaVersion')) is int and record['schemaVersion'] == 1
            and record.get('context') == context, 'EVALUATION_CONTEXT_MISMATCH')
    require(is_hash(record.get('inputSha256')) and is_hash(record.get('resultSha256')),
            'EVALUATION_PROVENANCE_REQUIRED')
    require(record.get('numericalStatus') in ('PASSED', 'FAILED')
            and type(record.get('complete')) is bool and isinstance(record.get('raw'), dict),
            'EVALUATION_RECORD_INVALID')
    for key, value in record['raw'].items():
        require(key in METRICS and (value is None or number(value) >= 0), 'EVALUATION_METRIC_INVALID')


def _compare(policy, baseline, alternative):
    for record in (baseline, alternative):
        validate_record(record, policy['context'])
    blockers = []
    for label, record in (('BASELINE', baseline), ('ALTERNATIVE', alternative)):
        if record['numericalStatus'] != 'PASSED':
            blockers.append(label + '_NUMERICAL_FAILURE')
        if not record['complete']:
            blockers.append(label + '_INCOMPLETE')
        for key in policy['requiredMetrics']:
            if record['raw'].get(key) is None:
                blockers.append(label + '_METRIC_MISSING_' + key)
    effects, values = {}, {}
    for key, rule in policy['metrics'].items():
        base, candidate = baseline['raw'].get(key), alternative['raw'].get(key)
        delta = (number(candidate) - number(base)) * METRICS[key][1] if base is not None and candidate is not None else None
        score = 100 * max(Fraction(-1), min(Fraction(1), delta / number(rule['reference']))) if delta is not None and not blockers else None
        effects[key] = {'unit': rule['unit'], 'baseline': base, 'alternative': candidate,
                        'improvement': encoded(delta) if delta is not None else None,
                        'score': encoded(score) if score is not None else None}
        if not blockers:
            values['improvement:' + key], values['score:' + key] = delta, score
    if not blockers:
        values['total'] = sum(number(rule['weight']) * values['score:' + key]
                              for key, rule in policy['metrics'].items())
    return effects, values, blockers


def compare(policy, baseline, alternative):
    policy_hash = validate_policy(policy)
    effects, values, blockers = _compare(policy, baseline, alternative)
    return {'schemaVersion': 1, 'policySha256': policy_hash, 'context': policy['context'],
            'baselineResultSha256': baseline['resultSha256'],
            'alternativeResultSha256': alternative['resultSha256'],
            'status': 'WITHHELD' if blockers else 'COMPUTED_DIAGNOSTIC',
            'rankingEligible': False, 'blockers': blockers, 'effects': effects,
            'total': encoded(values['total']) if not blockers else None}
