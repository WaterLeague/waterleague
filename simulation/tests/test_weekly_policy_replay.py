"""코드 갱신 뒤 기존 관측·점수의 완전 일치와 정책 변조 차단 검사."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from waterleague_sim.evaluation import score_policy as policy
from waterleague_sim.shared_physics import verify_replayed_prefix


class WeeklyPolicyReplayTests(unittest.TestCase):
    @patch('waterleague_sim.engine.continuous.engine_identity', return_value={'binarySha256': 'a'*64})
    def test_code_only_change_allows_replay_but_not_runtime_metric_or_archive_changes(self, engine):
        current = policy.freeze('WEEKLY', 'OBSERVED_ACCOUNTED_VOLUME_SECONDS_V2')
        archived = copy.deepcopy(policy.source_policy())
        archived['files']['simulation/waterleague_sim/weekly.py'] = 'b'*64
        raw = policy.encode(archived)
        previous = current | {'policySha256': policy.digest(raw)}
        previous['sha256'] = policy.digest(policy.encode({k: v for k, v in previous.items() if k != 'sha256'}))
        with tempfile.TemporaryDirectory() as root:
            path = Path(root)/'score-policy.json'
            path.write_bytes(raw)
            self.assertEqual(policy.replay_context(root, previous, current), previous)
            for field, value in [('runtime', {}), ('binding', 'OTHER'), ('mode', 'SUBMISSION'), ('sha256', 'c'*64)]:
                changed = previous | {field: value}
                if field != 'sha256':
                    changed['sha256'] = policy.digest(policy.encode({k: v for k, v in changed.items() if k != 'sha256'}))
                with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'LIVE_PREVIOUS_INPUT_INVALID'):
                    policy.replay_context(root, changed, current)
            changed = archived | {'weeklyDecimalPlaces': 8}
            path.write_bytes(policy.encode(changed))
            altered = previous | {'policySha256': policy.digest(path.read_bytes())}
            altered['sha256'] = policy.digest(policy.encode({k: v for k, v in altered.items() if k != 'sha256'}))
            with self.assertRaisesRegex(ValueError, 'LIVE_PREVIOUS_INPUT_INVALID'):
                policy.replay_context(root, altered, current)
            path.write_bytes(raw+b' ')
            with self.assertRaisesRegex(ValueError, 'LIVE_PREVIOUS_INPUT_INVALID'):
                policy.replay_context(root, previous, current)

    def test_every_existing_sample_and_contribution_must_match(self):
        old = {'contribution': [{'cumulativeM3': 1}, {'cumulativeM3': 2}],
               'baseline': {'samples': [{'water': 1}, {'water': 2}], 'final': {'water': 2}},
               'strategy': {'samples': [{'water': 0}, {'water': 1}], 'final': {'water': 1}}}
        current = copy.deepcopy(old)
        current['contribution'].append({'cumulativeM3': 3})
        for name in ('baseline', 'strategy'):
            current[name]['samples'].append({'water': 3})
        verify_replayed_prefix(old, current)
        for name in ('baseline', 'strategy', 'contribution'):
            changed = copy.deepcopy(current)
            if name == 'contribution':
                changed[name][0]['cumulativeM3'] += .01
            else:
                changed[name]['samples'][0]['water'] += .01
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'LIVE_PREVIOUS_STATE_CHANGED'):
                verify_replayed_prefix(old, changed)
