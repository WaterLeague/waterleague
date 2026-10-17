"""음의 효과·포화 점수·공동 상호작용·표본 오차·중단 재현 검사."""
from copy import deepcopy
from fractions import Fraction
import json
import unittest

from waterleague_sim.evaluation.attribution import attribute, permutation
from waterleague_sim.evaluation.exception import EvaluationError
from waterleague_sim.evaluation.service import METRICS, compare, validate_policy
from waterleague_sim.evaluation.values import digest


def policy():
    context = {'scopeId': 'NUMERICAL_ONLY', 'modelGrade': 'DRAFT', 'evidenceClass': 'NUMERICAL_TEST_ONLY',
        'comparisonKind': 'CURRENT', 'effectAreaId': 'REFERENCE_BASIN',
        **{key: digest(key) for key in ('scenarioSnapshotSha256', 'forcingSha256', 'engineSha256',
                                       'metricSpecificationSha256')}}
    metrics = {key: {'unit': unit, 'reference': '10', 'weight': '1' if index == 0 else '0',
                    'evidenceSha256': [digest('NUMERICAL_REFERENCE_ONLY')]}
               for index, (key, (unit, _)) in enumerate(list(METRICS.items())[:3])}
    return {'schemaVersion': 1, 'policyVersion': 'NUMERICAL_TEST_v1', 'context': context,
            'metrics': metrics, 'requiredMetrics': list(metrics)}


def record(profile, flow=1000, *, status='PASSED', complete=True):
    return {'schemaVersion': 1, 'context': deepcopy(profile['context']), 'inputSha256': digest(['input', flow]),
            'resultSha256': digest(['result', flow]), 'numericalStatus': status, 'complete': complete,
            'raw': {'outwardVolumeM3': flow, 'peakOutwardM3s': 1, 'depthAreaTimeM3Hours': 1}}


def members():
    return [{'memberId': 'a', 'districtCode': '11110', 'facilityIds': ['a-1', 'a-2']},
            {'memberId': 'b', 'districtCode': '11110', 'facilityIds': ['b-1']}]


def exact(row):
    return Fraction(row['exact'])


class EffectTests(unittest.TestCase):
    def test_raw_negative_and_saturation_keep_zero_baseline_valid(self):
        p = policy()
        improvement = compare(p, record(p), record(p, 0))
        self.assertEqual(exact(improvement['effects']['outwardVolumeM3']['improvement']), 1000)
        self.assertEqual(exact(improvement['total']), 100)
        worse = compare(p, record(p), record(p, 2000))
        self.assertEqual(exact(worse['effects']['outwardVolumeM3']['improvement']), -1000)
        self.assertEqual(exact(worse['total']), -100)
        self.assertEqual(exact(compare(p, record(p, 0), record(p, 0))['total']), 0)

    def test_failed_incomplete_and_missing_required_metric_withhold_total(self):
        p = policy()
        for alternative in (record(p, 0, status='FAILED'), record(p, 0, complete=False),
                            record(p, 0) | {'raw': {'outwardVolumeM3': 0, 'peakOutwardM3s': 1}}):
            result = compare(p, record(p), alternative)
            self.assertEqual(result['status'], 'WITHHELD')
            self.assertIsNone(result['total'])
            self.assertIsNone(result['effects']['outwardVolumeM3']['score'])
            self.assertEqual(exact(result['effects']['outwardVolumeM3']['improvement']), 1000)
            self.assertTrue(result['blockers'])

    def test_context_mismatch_rejected_for_every_fixed_condition(self):
        p = policy()
        for key in p['context']:
            alternative = record(p)
            alternative['context'][key] = 'different'
            with self.subTest(key=key), self.assertRaisesRegex(EvaluationError, 'CONTEXT_MISMATCH'):
                compare(p, record(p), alternative)

    def test_invalid_references_weights_units_required_list_and_nan_rejected(self):
        for key, value in [('reference', 0), ('weight', '.5'), ('unit', 'mm'), ('evidenceSha256', [])]:
            p = policy()
            p['metrics']['outwardVolumeM3'][key] = value
            with self.subTest(key=key), self.assertRaises(EvaluationError):
                validate_policy(p)
        p = policy()
        p['requiredMetrics'] = ['outwardVolumeM3'] * 3
        with self.assertRaises(EvaluationError):
            validate_policy(p)
        for invalid in (float('nan'), float('inf'), True, '-1', '1e999'):
            p = policy()
            r = record(p)
            r['raw']['outwardVolumeM3'] = invalid
            with self.subTest(value=invalid), self.assertRaises(EvaluationError):
                compare(p, record(p), r)

    def test_extended_metrics_require_evidence_and_preserve_benefit_direction(self):
        p = policy()
        for key, (unit, _) in METRICS.items():
            p['metrics'][key] = {'unit': unit, 'reference': 10, 'weight': '.2',
                                 'evidenceSha256': [digest('NUMERICAL_TEST_ONLY')]}
        p['requiredMetrics'] = list(METRICS)
        self.assertEqual(compare(p, record(p), record(p))['status'], 'WITHHELD')
        base, alternative = record(p), record(p)
        base['raw'].update(reusedVolumeM3=0, removedPollutantKg=0)
        alternative['raw'].update(reusedVolumeM3=5, removedPollutantKg=10)
        result = compare(p, base, alternative)
        self.assertEqual(exact(result['total']), 30)
        self.assertFalse(result['rankingEligible'])


class AttributionTests(unittest.TestCase):
    def setUp(self):
        self.profile = policy()
        self.seen = []

    def evaluate(self, selected, facilities):
        self.seen.append((selected, facilities))
        flows = {(): 1000, ('a',): 0, ('b',): 2000, ('a', 'b'): 0}
        return record(self.profile, flows[selected])

    def run_attribution(self, **kwargs):
        options = {'seed': '0' * 64, 'samples': 4, 'max_evaluations': 4} | kwargs
        return attribute(self.profile, members(), self.evaluate, **options)

    def test_nonlinear_score_attribution_negative_and_exact_sum_without_reclipping(self):
        result = self.run_attribution()
        self.assertEqual(result['status'], 'ESTIMATED_DIAGNOSTIC')
        self.assertEqual(exact(result['memberEstimates']['a']['total']['mean']), 175)
        self.assertEqual(exact(result['memberEstimates']['b']['total']['mean']), -75)
        self.assertEqual(result['memberEstimates']['a']['total']['standardError'], 25)
        self.assertEqual(result['districtEstimates']['11110']['total']['standardError'], 0)
        self.assertEqual(exact(result['conservation']['total']['districtSum']), 100)
        for row in result['conservation'].values():
            self.assertEqual(exact(row['memberSum']), exact(row['totalEffect']))
            self.assertEqual(exact(row['residual']), 0)
        self.assertEqual(len(self.seen), 4)
        self.assertIn((('a',), ('a-1', 'a-2')), self.seen)
        self.assertFalse(result['rankingEligible'])

    def test_deterministic_uniform_permutations_and_input_order(self):
        self.assertEqual(permutation(['a', 'b'], '0' * 64, 0), ['b', 'a'])
        self.assertEqual(permutation(['a', 'b'], '0' * 64, 1), ['a', 'b'])
        a_first = sum(permutation(['a', 'b'], '0' * 64, i)[0] == 'a' for i in range(1000))
        self.assertGreater(a_first, 450)
        self.assertLess(a_first, 550)
        first = self.run_attribution()
        second = attribute(self.profile, list(reversed(members())), self.evaluate,
                           seed='0' * 64, samples=4, max_evaluations=4)
        self.assertEqual(first, second)

    def test_budget_stop_uses_only_complete_permutations_and_cache_resume(self):
        cache = {}
        partial = self.run_attribution(cache=cache, max_evaluations=3)
        self.assertEqual(partial['status'], 'WITHHELD')
        self.assertEqual(partial['completedPermutations'], 1)
        self.assertEqual(partial['failureCode'], 'ATTRIBUTION_EVALUATION_LIMIT')
        self.assertIsNone(partial['memberEstimates']['a']['total']['standardError'])
        self.assertEqual(partial['pendingCoalition']['memberIds'], ['a'])
        resumed = self.run_attribution(cache=cache, max_evaluations=1)
        fresh = self.run_attribution()
        self.assertEqual(resumed['newEvaluations'], 1)
        for key in ('memberEstimates', 'districtEstimates', 'conservation', 'permutations', 'coalitionEvaluations'):
            self.assertEqual(resumed[key], fresh[key])

    def test_cache_corruption_and_different_policy_never_reuse_results(self):
        cache = {}
        self.run_attribution(cache=cache)
        key = next(iter(cache))
        cache[key]['record']['raw']['outwardVolumeM3'] = 5
        corrupted = self.run_attribution(cache=cache)
        self.assertEqual(corrupted['failureCode'], 'ATTRIBUTION_CACHE_MISMATCH')
        self.profile['context']['forcingSha256'] = digest('new forcing')
        self.assertEqual(self.run_attribution(cache=cache)['newEvaluations'], 4)

    def test_failed_coalition_not_skipped_or_averaged(self):
        def failed(selected, facilities):
            r = self.evaluate(selected, facilities)
            if selected == ('b',):
                r['numericalStatus'] = 'FAILED'
            return r
        result = attribute(self.profile, members(), failed, seed='0' * 64, samples=4, max_evaluations=4)
        self.assertEqual(result['failureCode'], 'ATTRIBUTION_COALITION_INCOMPLETE')
        self.assertEqual(result['completedPermutations'], 0)
        self.assertEqual(result['memberEstimates'], {})
        self.assertTrue(any(row['record']['numericalStatus'] == 'FAILED'
                            for row in result['coalitionEvaluations'].values()))

    def test_callback_failure_redacted_and_ownership_overlap_rejected(self):
        def failed(*_):
            raise RuntimeError('secret-token-and-private-path')
        result = attribute(self.profile, members(), failed, seed='0' * 64, samples=4, max_evaluations=4)
        self.assertEqual(result['failureCode'], 'COALITION_EVALUATION_FAILED')
        self.assertNotIn('secret-token', json.dumps(result))
        overlapping = members()
        overlapping[1]['facilityIds'] = ['a-1']
        with self.assertRaisesRegex(EvaluationError, 'OWNERSHIP_INVALID'):
            attribute(self.profile, overlapping, self.evaluate, seed='0' * 64, samples=4, max_evaluations=4)
        self.assertEqual(self.seen, [])

    def test_dummy_player_and_fractional_additive_values_have_zero_error(self):
        rows = members() + [{'memberId': 'dummy', 'districtCode': '11200', 'facilityIds': ['dummy-1']}]
        def additive(selected, _):
            delta = ('.1' if 'a' in selected else '0'), ('.2' if 'b' in selected else '0')
            return record(self.profile, str(10 - sum(Fraction(v) for v in delta)))
        # 원본 10진 문자열을 사용하며 유리수 표기 문자열은 계산 입력으로 받지 않는다.
        def decimal_record(selected, owned):
            r = additive(selected, owned)
            r['raw']['outwardVolumeM3'] = float(Fraction(r['raw']['outwardVolumeM3']))
            return r
        result = attribute(self.profile, rows, decimal_record, seed='0' * 64, samples=32, max_evaluations=8)
        self.assertEqual(result['status'], 'ESTIMATED_DIAGNOSTIC')
        self.assertEqual(exact(result['memberEstimates']['a']['total']['mean']), 1)
        self.assertEqual(exact(result['memberEstimates']['b']['total']['mean']), 2)
        self.assertEqual(exact(result['memberEstimates']['dummy']['total']['mean']), 0)
        self.assertTrue(all(row['total']['standardError'] == 0 for row in result['memberEstimates'].values()))


if __name__ == '__main__':
    unittest.main()
