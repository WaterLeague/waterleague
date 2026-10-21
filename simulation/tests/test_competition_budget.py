"""원형 설치 계산의 대회 예산 고정과 일반 정책 보존 검사."""
import copy
import json
from pathlib import Path
import unittest
from waterleague_sim.installation_model import resolve


class CompetitionBudgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        site = json.loads((Path(__file__).resolve().parents[2] /
            'frontend/src/domains/installation/__tests__/fixtures/nativeSites.json').read_bytes())['reference']
        cls.installation = {'district_id': site['districtId'], 'cell_id': site['cellId'], 'model_hash': site['modelHash']}
        cls.original, _, _ = resolve(cls.installation)
        cls.policy = cls.original['budgetPolicy'] | {'limitKrw': 3_000_000_000,
            'personalLimitKrw': 3_000_000_000, 'ruleVersion': 'COMPETITION_PERSONAL_V1',
            'sourceTitle': '예산 검증 대회', 'sourceSha256': 'c' * 64,
            'sourceUrl': 'https://waterleague.cloud/competitions/12345678-1234-1234-1234-123456789012'}

    def test_custom_budget_changes_only_frozen_budget_and_keeps_native_model(self):
        model, station, name = resolve(self.installation | {'budget_policy': json.dumps(self.policy)})
        self.assertEqual(model['budget'], 3_000_000_000)
        self.assertEqual(model['budgetPolicy'], self.policy)
        self.assertTrue(station and name)
        self.assertEqual({k: v for k, v in model.items() if k not in ('budget', 'budgetPolicy')},
                         {k: v for k, v in self.original.items() if k not in ('budget', 'budgetPolicy')})
        self.assertEqual(resolve(self.installation)[0]['budget'], 2_000_000_000)

    def test_invalid_frozen_limit_or_source_is_rejected(self):
        for changed in ({'personalLimitKrw': 0}, {'personalLimitKrw': 1.5},
                        {'personalLimitKrw': 1_000_000_000_001}, {'limitKrw': 1},
                        {'allocationScope': 'DISTRICT'}, {'sourceSha256': 'missing'},
                        {'sourceUrl': 'https://other.invalid/competition'}):
            with self.subTest(changed=changed), self.assertRaisesRegex(ValueError, 'LIVE_BUDGET_POLICY_INVALID'):
                resolve(self.installation | {'budget_policy': self.policy | changed})
        altered = copy.deepcopy(self.original['budgetPolicy'])
        altered['personalLimitKrw'] += 1
        with self.assertRaisesRegex(ValueError, 'LIVE_BUDGET_POLICY_INVALID'):
            resolve(self.installation | {'budget_policy': altered})
