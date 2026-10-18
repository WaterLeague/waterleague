"""견적 합계·미산정 원가·정확한 용량 연결과 기존 물리 입력 불변 검사."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from waterleague_sim.costing.cistern import estimate, CATALOG_PATH, CATALOG_SHA256
from waterleague_sim.engine.connected_facilities import compile_design
from waterleague_sim.engine.priced_facilities import compile_priced_design
from waterleague_sim.engine.flood_errors import FloodModelError
from waterleague_sim.engine.flood_process import EngineProcess
from waterleague_sim.engine import facility_network
from waterleague_sim.ingestion.published_network import digest
from tests.test_connected_facilities import SOURCE, baseline

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).parent / 'fixtures'
DESIGN = json.loads((FIXTURES / 'priced-cisterns-v1.json').read_text())
COST = json.loads((FIXTURES / 'priced-cistern-request-v1.json').read_text())


class PricedFacilityTests(unittest.TestCase):
    def test_quote_components_reconcile_without_inventing_missing_prices(self):
        for quote, total, materials, difference in (
            ('A', 5447000, 5149000, 298000), ('B', 3512000, 2961000, 551000),
            ('C', 2857000, 2857000, 0),
        ):
            result = estimate(quote, 3)
            initial = result['initial']
            self.assertEqual(initial['quotedSubtotalKrw'], total * 3)
            self.assertEqual(initial['materialsKrw'], materials * 3)
            self.assertEqual(initial['unclassifiedDifferenceKrw'], difference * 3)
            self.assertEqual(sum(row['amountKrw'] or 0 for row in initial['components'])
                             + difference * 3, total * 3)
            self.assertIsNone(initial['completeInstalledCostKrw'])
            self.assertIsNone(result['source']['priceYear'])
            self.assertEqual(result['source']['publicationYear'], 2018)
            self.assertFalse(result['currentPriceEligible'])
            self.assertFalse(result['historicalPriceEligible'])
            self.assertFalse(result['eligibleForBudgetCharge'])
        missing = next(c for c in estimate('C', 1)['initial']['components'] if c['id'] == 'LOG')
        self.assertIsNone(missing['amountKrw'])
        self.assertEqual(missing['status'], 'NOT_SEPARATELY_STATED')

    def test_annual_cost_is_separate_from_capital_and_capacity_not_area_priced(self):
        one, two = estimate('C', 1), estimate('C', 2)
        self.assertEqual(one['annualOperation']['estimatedKrw'], 107140)
        self.assertEqual(two['annualOperation']['estimatedKrw'], 214280)
        self.assertEqual(two['initial']['quotedSubtotalKrw'], 5714000)
        self.assertEqual(two['totalCapacityM3'], '4.70')
        self.assertEqual(two['quoteRange']['minimumKrw'], 5714000)
        self.assertEqual(two['quoteRange']['maximumKrw'], 10894000)
        for bad in (0, -1, 257, True, 1.0, '2', float('nan')):
            with self.assertRaises(FloodModelError):
                estimate('C', bad)
        for bad in ('D', 'c', None, [], 2):
            with self.assertRaises(FloodModelError):
                estimate(bad, 1)

    def test_exact_design_binding_partial_costs_and_physics_unchanged(self):
        original, physical = compile_design(SOURCE, DESIGN)
        priced, metadata = compile_priced_design(SOURCE, DESIGN, COST)
        self.assertEqual(priced, original)
        self.assertEqual({k: metadata[k] for k in physical}, physical)
        costs = metadata['costing']
        self.assertEqual(costs['knownQuotedSubtotalKrw'], 5714000)
        self.assertEqual(costs['knownAnnualOperationEstimateKrw'], 214280)
        self.assertEqual(costs['unpricedPlacementIds'], ['Bioretention'])
        self.assertIsNone(costs['completeInstalledCostKrw'])
        self.assertEqual(costs['estimates'][0]['units'], 2)
        self.assertEqual(compile_priced_design(SOURCE, DESIGN, COST), (priced, metadata))
        other_quote = deepcopy(COST)
        other_quote['items'][0]['quoteId'] = 'A'
        raw, other = compile_priced_design(SOURCE, DESIGN, other_quote)
        self.assertEqual(raw, original)
        self.assertNotEqual(other['costingSha256'], metadata['costingSha256'])
        self.assertEqual(other['costing']['knownQuotedSubtotalKrw'], 8304000)
        empty = compile_priced_design(SOURCE, DESIGN, {**COST, 'items': []})[1]['costing']
        self.assertEqual(empty['knownQuotedSubtotalKrw'], 0)
        self.assertEqual(len(empty['unpricedPlacementIds']), 3)
        self.assertIsNone(empty['completeInstalledCostKrw'])

    def test_wrong_volume_one_large_tank_duplicate_or_wrong_facility_rejected(self):
        for depth in (1000.001, 2000, 8500):
            changed = deepcopy(DESIGN)
            changed['placements'][1]['parameters']['storageDepthMm'] = depth
            with self.assertRaisesRegex(FloodModelError, 'CAPACITY_MISMATCH'):
                compile_priced_design(SOURCE, changed, COST)
        for changes in (
            {'catalogSha256': '0' * 64},
            {'items': COST['items'] * 2},
            {'items': [{'placementId': 'missing', 'quoteId': 'C'}]},
            {'items': [{'placementId': 'Bioretention', 'quoteId': 'C'}]},
            {'items': [{'placementId': 'CisternOne', 'quoteId': 'C', 'unitCostKrw': 1}]},
        ):
            with self.assertRaises(FloodModelError):
                compile_priced_design(SOURCE, DESIGN, {**COST, **changes})
        self.assertEqual(digest(CATALOG_PATH.read_bytes()), CATALOG_SHA256)

    @unittest.skipUnless(facility_network.library_path().exists(), '연결 시설 네이티브 빌드 필요')
    def test_native_individual_capacity_and_cost_only_change_preserves_output(self):
        source = baseline()
        raw, metadata = compile_priced_design(source, DESIGN, COST)
        second = deepcopy(COST)
        second['items'][0]['quoteId'] = 'A'
        alternate, other = compile_priced_design(source, DESIGN, second)
        with tempfile.TemporaryDirectory(dir=ROOT / 'tmp', prefix='priced-lid-') as temporary:
            directory = Path(temporary)
            results = []
            for name, data in (('c', raw), ('a', alternate)):
                with EngineProcess('facility_network', data.decode(), directory / name, native_duration=True) as process:
                    results.append(process.call('run', 300)['result'])
            self.assertEqual((directory / 'c/network.out').read_bytes(), (directory / 'a/network.out').read_bytes())
            self.assertEqual(results[0]['final'], results[1]['final'])
            self.assertEqual(results[0]['numericalStatus'], 'PASSED')
            tanks = [r for r in results[0]['final']['facilities'] if r['swmmId'].startswith('WL_Cistern')]
            self.assertEqual(len(tanks), 2)
            for tank in tanks:
                self.assertAlmostEqual(tank['finalStorageM3'], 2.35, places=8)
                self.assertEqual(tank['drainOutflowM3'], 0)
                self.assertGreater(tank['surfaceOutflowM3'], 0)
                self.assertEqual(tank['numericalStatus'], 'PASSED')
            self.assertNotEqual(metadata['costingSha256'], other['costingSha256'])


if __name__ == '__main__':
    unittest.main()
