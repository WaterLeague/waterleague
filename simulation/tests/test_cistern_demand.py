"""수요 인출의 가용 물 한도·기간 경계·기본 배수 결과 보존 검사."""
import copy
import ctypes as C
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from test_cistern_game import fixture
from waterleague_sim.engine import cistern_demand as demand, continuous, initialization, swmm
from waterleague_sim.engine.swmm import SimulationQualityError


class CisternDemandTests(unittest.TestCase):
    def test_constant_demand_with_full_tank_supplies_201_litres_over_exact_day(self):
        model, placement = fixture([2] * 30 + [0] * 1440)
        installed = (datetime.fromisoformat(model['rainfall']['start']) + timedelta(minutes=30)).isoformat()
        with tempfile.TemporaryDirectory() as root:
            result = continuous.experiment(model, placement, root, installed_at=installed)
            value = result['cistern']['demandScenario']
            self.assertEqual(value['evaluationSeconds'], 86400)
            self.assertAlmostEqual(value['demandM3'], .201, places=14)
            self.assertAlmostEqual(value['suppliedM3'], .201, places=10)
            self.assertAlmostEqual(value['unmetDemandM3'], 0, places=10)
            self.assertGreater(value['initialStorageM3'], 2.34)
            self.assertLess(abs(value['balanceResidualM3']), .001)
            self.assertFalse(value['rankingEligible'])
            self.assertIsNone(value['observedReuseM3'])
            self.assertIsNone(result['cistern']['reuseM3'])
            self.assertEqual(value['evaluationStart'], result['strategy']['initial']['at'])
            self.assertEqual(value['evaluationEnd'], result['strategy']['final']['at'])
            self.assertNotEqual(value['suppliedM3'], result['cistern']['drainageM3'])
            archive = json.loads((Path(root) / 'cistern-demand-run.json').read_text())
            self.assertEqual(archive['scenario'], value)
            manifest = json.loads((Path(root) / 'manifest.json').read_text())
            for name in ('cistern_demand.inp', 'cistern_demand.rpt', 'cistern_demand.out',
                         'cistern-demand.json', 'cistern_demand.py', 'cistern-demand-run.json'):
                self.assertEqual(manifest[name], continuous.digest((Path(root) / name).read_bytes()))

    def test_empty_or_insufficient_tank_does_not_supply_unavailable_water(self):
        with tempfile.TemporaryDirectory() as root:
            for rain in ([0] * 1440, [2] + [0] * 1439):
                model, placement = fixture(rain)
                value = demand.analyze(model, placement, root, None)
                self.assertAlmostEqual(value['demandM3'], .201)
                self.assertLessEqual(value['suppliedM3'], value['inflowM3'])
                self.assertAlmostEqual(value['suppliedM3'] + value['unmetDemandM3'], .201)
                if not any(rain):
                    self.assertEqual(value['suppliedM3'], 0)
                    self.assertEqual(value['supplyFraction'], 0)
                else:
                    self.assertGreater(value['suppliedM3'], 0)
                    self.assertGreater(value['unmetDemandM3'], 0)

    def test_partial_full_roof_and_prefix_preserve_supply_and_storage(self):
        with tempfile.TemporaryDirectory() as root:
            for area in (235, 470.125):
                model, placement = fixture([2] * 30 + [0] * 30, area)
                longer, _ = fixture([2] * 30 + [0] * 120, area)
                short = continuous.replay(model, [placement], root, 'short', cistern_scenario=demand.IDENTIFIER)
                long = continuous.replay(longer, [placement], root, 'long', cistern_scenario=demand.IDENTIFIER)
                self.assertEqual(short['samples'], long['samples'][:60])
                self.assertTrue(all(0 <= s['lidStorageM3'] <= area * .01 + 1e-8 for s in long['samples']))
                result = continuous.experiment(model, placement, root)
                scenario = result['cistern']['demandScenario']
                self.assertAlmostEqual(scenario['demandRateM3Day'], .201 * area / 235)
                primary = continuous.replay(model, [placement], root, 'unchanged')
                self.assertEqual(result['strategy'], primary)
                self.assertEqual((Path(root) / 'strategy.inp').read_bytes(),
                                 (Path(root) / 'unchanged.inp').read_bytes())

    def test_seven_day_preparation_and_installation_seconds_excluded_without_reset(self):
        minutes = initialization.MINUTES
        model, placement = fixture([2] * 30 + [0] * (minutes + 10 - 30))
        start = datetime.fromisoformat(model['rainfall']['start'])
        model['initialization'] = {'method': initialization.METHOD, 'warmupMinutes': minutes,
            'evaluationStart': (start + timedelta(minutes=minutes)).isoformat(), 'limitations': []}
        offset = minutes * 60 + 137
        with tempfile.TemporaryDirectory() as root:
            value = demand.analyze(model, placement, root, None, evaluation_start_seconds=offset)
            archive = json.loads((Path(root) / 'cistern-demand-run.json').read_text())['run']
            self.assertEqual(value['evaluationSeconds'], 463)
            self.assertEqual(value['initialStorageM3'], archive['preActivation']['final']['lidStorageM3'])
            self.assertGreater(value['initialStorageM3'], .9)
            self.assertAlmostEqual(value['suppliedM3'], .201 * 463 / 86400, places=10)
            whole = demand.analyze(model, placement, root, None)
            self.assertEqual(whole['evaluationSeconds'], 600)
            self.assertAlmostEqual(whole['demandM3'], .201 * 600 / 86400)
            self.assertGreater(whole['initialStorageM3'], value['initialStorageM3'])

    def test_invalid_scenario_facility_source_and_balance_fail_closed(self):
        model, placement = fixture([1] * 2)
        with tempfile.TemporaryDirectory() as root:
            for selected in ([], [placement | {'facilityType': 'GREEN_ROOF'}]):
                with self.assertRaisesRegex(SimulationQualityError, 'CISTERN_DEMAND_PLACEMENT_REQUIRED'):
                    continuous.replay(model, selected, root, 'invalid', cistern_scenario=demand.IDENTIFIER)
            with self.assertRaisesRegex(SimulationQualityError, 'CISTERN_DEMAND_SCENARIO_INVALID'):
                continuous.replay(model, [placement], root, 'invalid', cistern_scenario='arbitrary')
            for area in (True, 0, float('nan'), float('inf')):
                with self.assertRaises(SimulationQualityError):
                    demand.parameters(demand.IDENTIFIER, area, 2.35)
            forged = Path(root) / 'catalog.json'
            forged.write_text('{}')
            with patch.object(demand, 'PATH', forged), self.assertRaisesRegex(
                    SimulationQualityError, 'CISTERN_DEMAND_CATALOG_INVALID'):
                demand.catalog()
            run = continuous.replay(model, [placement], root, 'valid', cistern_scenario=demand.IDENTIFIER)
            changed = copy.deepcopy(run)
            changed['final']['lidDrainageTotalM3'] = 100
            with self.assertRaisesRegex(SimulationQualityError, 'CISTERN_DEMAND_BALANCE_INVALID'):
                demand.summarize(changed, placement, '0' * 64)

    def test_separate_unmodified_epa_build_produces_identical_binary_output(self):
        model, placement = fixture([2] * 30 + [0] * 90)
        with tempfile.TemporaryDirectory() as root:
            path = Path(root)
            continuous.replay(model, [placement], path, 'scenario', cistern_scenario=demand.IDENTIFIER)
            library = C.CDLL(str(swmm.library_path()))
            self.assertEqual(library.swmm_run(os.fsencode(path / 'scenario.inp'),
                os.fsencode(path / 'reference.rpt'), os.fsencode(path / 'reference.out')), 0)
            self.assertEqual((path / 'scenario.out').read_bytes(), (path / 'reference.out').read_bytes())


if __name__ == '__main__':
    unittest.main()
