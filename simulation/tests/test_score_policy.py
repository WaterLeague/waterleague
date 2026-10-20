"""평가 전 조건 동결·정밀도·원문 변조의 순위 차단 검사."""
import copy
from decimal import Decimal
import unittest
from unittest.mock import patch
from waterleague_sim.evaluation import score_policy as policy


class ScorePolicyTests(unittest.TestCase):
    def test_committed_code_and_policy_match(self):
        raw, value = policy.verified_policy()
        self.assertEqual(raw, policy.encode(policy.source_policy()))
        self.assertFalse(value['relativeUsedForRanking'])
        self.assertIsNone(value['compositeScore'])
        self.assertIn('simulation/waterleague_sim/weekly.py', value['files'])
        self.assertIn('backend/src/main/java/io/waterleague/weekly/service/WeeklyService.java', value['files'])

    def test_half_even_boundaries_signed_values_and_small_improvement(self):
        for value, expected in [('1.0000000005', '1.000000000'), ('1.0000000015', '1.000000002'),
                                ('-1.0000000015', '-1.000000002'), ('0', '0.000000000'),
                                ('-0.000000001', '-0.000000001')]:
            self.assertEqual(format(policy.quantize(value, 9), 'f'), expected)
        self.assertLess(policy.quantize('1', 9), policy.quantize('1.000000001', 9))
        self.assertEqual(policy.quantize('0.0000000000000000005', 18), Decimal(0))
        self.assertEqual(policy.quantize('0.0000000000000000015', 18), Decimal('0.000000000000000002'))
        for value in ('NaN', 'Infinity', '1e15', True):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'LIVE_SCORE_VALUE_INVALID'):
                policy.quantize(value, 18)

    @patch('waterleague_sim.engine.continuous.engine_identity', return_value={'binarySha256': 'a'*64})
    def test_frozen_runtime_mode_and_time_rule_are_comparison_boundaries(self, engine):
        context = policy.freeze('WEEKLY', 'OBSERVED_ACCOUNTED_VOLUME_SECONDS_V2')
        self.assertEqual(policy.verify(context, 'WEEKLY', context['binding']), context)
        for field in ('sha256', 'policySha256', 'binding', 'mode'):
            changed = copy.deepcopy(context); changed[field] = 'changed'
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'LIVE_SCORE_CONTEXT_INVALID'):
                policy.verify(changed, 'WEEKLY', context['binding'])
        other = policy.freeze('WEEKLY', 'OBSERVED_ACCOUNTED_VOLUME_V1')
        self.assertNotEqual(other['sha256'], context['sha256'])
        engine.return_value = {'binarySha256': 'b'*64}
        with self.assertRaisesRegex(ValueError, 'LIVE_SCORE_CONTEXT_INVALID'):
            policy.verify(context, 'WEEKLY', context['binding'])

    def test_source_profile_change_is_rejected_before_evaluation(self):
        value = policy.source_policy(); value['files']['simulation/waterleague_sim/weekly.py'] = 'a'*64
        with patch.object(policy, 'source_policy', return_value=value):
            with self.assertRaisesRegex(ValueError, 'LIVE_SCORE_POLICY_INVALID'):
                policy.verified_policy()
        with patch.object(policy, '_LOADED_FILES', {}):
            with self.assertRaisesRegex(ValueError, 'LIVE_SCORE_POLICY_INVALID'):
                policy.verified_policy()

    def test_submission_without_frozen_policy_is_rejected_before_engine(self):
        import json
        import tempfile
        from pathlib import Path
        from waterleague_sim.run_historical_submission import calculate, POLICY
        rules = {'policy': POLICY}
        rules_raw = json.dumps(rules)
        rows = [{'submissionPolicy': POLICY, 'submissionRulesRaw': rules_raw,
                 'submissionRulesHash': policy.digest(rules_raw.encode())}]
        body = json.dumps(rows)
        request = {'modelHash': 'a'*64, 'placements': body,
                   'inputHash': policy.digest(('a'*64+'\n'+body).encode())}
        with tempfile.TemporaryDirectory() as folder, patch('waterleague_sim.run_historical_submission.district_calculate') as engine:
            with self.assertRaisesRegex(ValueError, 'HISTORICAL_SUBMISSION_RULES_INVALID'):
                calculate(request, Path(folder))
            engine.assert_not_called()
