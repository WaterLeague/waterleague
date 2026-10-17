"""Java 고정 벡터와 독립 생성 재생기의 교차 검증."""
import copy
from decimal import Decimal
from pathlib import Path
import unittest
from waterleague_sim.optimization.replay import decoded, verify

ROOT = Path(__file__).resolve().parents[2]


class SearchReplayTests(unittest.TestCase):
    def setUp(self):
        self.model = (ROOT / 'data/models/seongsu-lab.json').read_bytes()
        self.report = decoded((ROOT / 'simulation/tests/fixtures/pattern-search-v1.json').read_bytes())

    def test_replays_java_elites_frequencies_draws_costs_and_hashes(self):
        result = verify(self.model, self.report)
        self.assertEqual((result['requestedCount'], result['uniquePhysicalCount'], result['trainingCount']), (5, 4, 3))
        self.assertEqual(len(result['candidates']), 8)
        self.assertEqual(result['sources'][0]['physicalHash'], result['sources'][1]['physicalHash'])

    def test_rejects_tampered_generation_claims(self):
        for field in ['inputHash', 'placementsSource', 'costKrw', 'attempt']:
            candidate = copy.deepcopy(self.report)
            candidate['candidates'][0][field] = 'invalid' if field in ('inputHash', 'placementsSource') else 999
            with self.assertRaises(ValueError, msg=field):
                verify(self.model, candidate)
        for field in ['trainingCount', 'sharedCandidateCount', 'drawLimit']:
            candidate = copy.deepcopy(self.report)
            candidate[field] = 999
            with self.assertRaises(ValueError, msg=field):
                verify(self.model, candidate)
        candidate = copy.deepcopy(self.report)
        candidate['distributions'][0]['options'][0]['patternWeight'] += 1
        with self.assertRaises(ValueError):
            verify(self.model, candidate)

    def test_rejects_altered_sources_seed_budget_and_model(self):
        for mutate in [
            lambda r: r['sources'][0]['sample'].update(inputHash='0' * 64),
            lambda r: r['sources'][1]['sample'].update(score=Decimal(11)),
            lambda r: r['sources'][0]['sample'].update(costKrw=0),
            lambda r: r['sources'][0]['sample'].update(costKrw=Decimal('1e10000000')),
            lambda r: r['settings'].update(seed=43),
            lambda r: r['settings'].update(budgetKrw=1),
            lambda r: r['settings'].update(candidatesPerArm=1000000),
        ]:
            candidate = copy.deepcopy(self.report)
            mutate(candidate)
            with self.assertRaises(ValueError):
                verify(self.model, candidate)
        with self.assertRaises(ValueError):
            verify(self.model + b'\n', self.report)

    def test_rejects_ambiguous_json(self):
        for raw in [b'{"seed":1,"seed":2}', b'{"cost":NaN}', b'{"cost":Infinity}']:
            with self.assertRaises(ValueError):
                decoded(raw)


if __name__ == '__main__':
    unittest.main()
