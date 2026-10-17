"""실제 두 엔진의 교환 방향·체적·시간 수렴과 잘못된 연결 거부 검사."""
from copy import deepcopy
from importlib.util import find_spec
import json
from pathlib import Path
import tempfile
import unittest

from waterleague_sim.engine.coupled_flood import run_coupled
from waterleague_sim.engine.flood_errors import FloodModelError
from waterleague_sim.engine.flood_process import EngineProcess
from waterleague_sim.engine.network_exchange import library_path
from waterleague_sim.reference.flood_cases import coupled_case, coupled_slope_case, coupled_limited_case


@unittest.skipUnless(find_spec('anuga') and library_path().exists(), '결합 엔진 설치 필요')
class CoupledFloodTests(unittest.TestCase):
    def test_surcharge_reentry_and_time_refinement(self):
        with tempfile.TemporaryDirectory() as root:
            results = []
            for step in (200, 100, 50):
                path = Path(root) / str(step)
                result = run_coupled(coupled_case(exchange_ms=step), path)
                results.append(result)
                b = result['balance']
                self.assertGreater(b['networkToSurfaceM3'], .1)
                self.assertGreater(b['surfaceToNetworkM3'], .1)
                self.assertLess(abs(b['exchangeCancellationResidualM3']), 1e-10)
                self.assertEqual(result['numericalStatus'], 'PASSED')
                surface = json.loads((path / 'surface/surface-result.json').read_text())
                self.assertGreaterEqual(min(surface['final']['depthM']), 0)
                self.assertLess(abs(b['balanceResidualM3']), .02)
            coarse, medium, fine = [r['balance']['surfaceStorageM3'] for r in results]
            self.assertLess(abs(medium - fine), abs(coarse - fine))
            self.assertLess(abs(medium - fine), .002)

    def test_dry_idle_and_rainfall_have_no_infinite_boundary_supply(self):
        with tempfile.TemporaryDirectory() as root:
            model = coupled_case(initial_network=0)
            model['durationSeconds'] = 5
            idle = run_coupled(model, Path(root) / 'idle')
            self.assertEqual(idle['balance']['surfaceToNetworkM3'], 0)
            self.assertEqual(idle['balance']['networkToSurfaceM3'], 0)
            self.assertEqual(idle['balance']['surfaceStorageM3'], 0)
            model['surfaceRainfall'] = [{'timeMilliseconds': 0, 'ratesMmH': [60.] * len(model['surface']['triangles']),
                                        'evidence': 'NUMERICAL_TEST_ONLY'}]
            rain = run_coupled(model, Path(root) / 'rain')
            self.assertAlmostEqual(rain['balance']['surfaceExternalNetInflowM3'], 4 * 60 / 3_600_000 * 5, places=12)
            self.assertGreater(rain['balance']['surfaceToNetworkM3'], 0)
            self.assertLess(abs(rain['balance']['balanceResidualM3']), 1e-4)

    def test_invalid_overlap_datums_and_ports_are_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            model = coupled_case()
            wrong = deepcopy(model)
            wrong['network']['verticalDatum'] = 'OTHER_DATUM'
            with self.assertRaisesRegex(FloodModelError, 'REFERENCE_MISMATCH'):
                run_coupled(wrong, Path(root) / 'datum')
            wrong = deepcopy(model)
            wrong['surface']['rainfallOwner'][0] = 'NETWORK'
            with self.assertRaisesRegex(FloodModelError, 'OWNERSHIP_INCOMPLETE'):
                run_coupled(wrong, Path(root) / 'owner')
            wrong = deepcopy(model)
            wrong['ports'].append(wrong['ports'][0] | {'id': 'second'})
            with self.assertRaisesRegex(FloodModelError, 'PORT_REGION_INVALID'):
                with EngineProcess('surface_exchange', wrong, Path(root) / 'overlap'):
                    pass
            wrong = deepcopy(model)
            wrong['ports'][0]['orifice'] = 'missing'
            with self.assertRaises(FloodModelError):
                run_coupled(wrong, Path(root) / 'pipe')
            wrong = deepcopy(model)
            wrong['network']['inputText'] = wrong['network']['inputText'].replace('ROUTING_STEP 0.01', 'ROUTING_STEP 0.0105')
            with self.assertRaisesRegex(FloodModelError, 'MILLISECOND_ROUTING_REQUIRED'):
                run_coupled(wrong, Path(root) / 'fractional-clock')

    def test_surface_withdrawal_is_atomic_and_reproducible(self):
        with tempfile.TemporaryDirectory() as root:
            model = coupled_case(initial_surface=.1)
            for i in range(2):
                with EngineProcess('surface_exchange', model, Path(root) / str(i)) as surface:
                    start = surface.call('port_state')
                    self.assertAlmostEqual(start['ports']['inlet']['availableM3'], .4, places=12)
                    applied = surface.call('apply_exchange', {'inlet': -.2})
                    self.assertAlmostEqual(applied['state']['storageM3'], .2, places=12)
                    applied = surface.call('apply_exchange', {'inlet': .3})
                    self.assertAlmostEqual(applied['state']['storageM3'], .5, places=12)
                    surface.call('advance_exchange', 100)
                    current = surface.call('snapshot')
                    if i == 0:
                        expected = current
                    else:
                        self.assertEqual(current, expected)
                    with self.assertRaisesRegex(FloodModelError, 'SURFACE_OVERDRAW'):
                        surface.call('apply_exchange', {'inlet': -1.})

    def test_local_surcharge_wets_dry_downhill_cells(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'slope'
            model = coupled_slope_case()
            result = run_coupled(model, path)
            surface = json.loads((path / 'surface/surface-result.json').read_text())
            final = surface['final']
            outside = set(range(len(final['depthM']))) - set(model['ports'][0]['surfaceTriangles'])
            self.assertGreater(sum(final['depthM'][i] > .001 for i in outside), 30)
            self.assertGreater(max(abs(v) for v in final['velocityXMps']), .05)
            self.assertEqual(result['numericalStatus'], 'PASSED')
            self.assertLess(abs(result['balance']['exchangeCancellationResidualM3']), 1e-10)

    def test_known_network_continuity_failure_is_not_promoted(self):
        with tempfile.TemporaryDirectory() as root:
            result = run_coupled(coupled_case(conduit=True), Path(root) / 'conduit')
            self.assertEqual(result['numericalStatus'], 'FAILED')
            self.assertEqual(result['networkNumericalStatus'], 'FAILED')
            self.assertLess(abs(result['balance']['exchangeCancellationResidualM3']), 1e-10)

    def test_available_surface_water_reduces_exchange_step(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'limited'
            result = run_coupled(coupled_limited_case(), path)
            self.assertLess(result['smallestExchangeMilliseconds'], 200)
            self.assertLessEqual(result['balance']['surfaceToNetworkM3'], .002 + 1e-12)
            self.assertGreater(result['balance']['surfaceToNetworkM3'], .001)
            rows = [json.loads(line) for line in (path / 'exchange-ledger.jsonl').read_text().splitlines()]
            for row in rows:
                if row['phase'] == 'NETWORK_ADVANCED':
                    for transfer in row['transfers']:
                        self.assertLessEqual(transfer['surfaceToNetworkM3'], transfer['availableBeforeM3'])
            self.assertEqual(result['numericalStatus'], 'PASSED')

    def test_output_frame_frequency_does_not_change_physics(self):
        with tempfile.TemporaryDirectory() as root:
            for i, frame in enumerate((50, 1000)):
                model = coupled_limited_case()
                model['frameIntervalMilliseconds'] = frame
                path = Path(root) / str(i)
                result = run_coupled(model, path)
                state = json.loads((path / 'surface/surface-result.json').read_text())['final']
                actual = (result['balance'], result['steps'], state)
                if i == 0:
                    expected = actual
                else:
                    self.assertEqual(actual, expected)

    def test_unmapped_network_flooding_preserves_failed_step(self):
        with tempfile.TemporaryDirectory() as root:
            model = coupled_case(initial_network=4.9)
            model['durationSeconds'] = 5
            model['networkForcing'] = [{'timeMilliseconds': 0, 'node': 'TANK', 'flowM3s': 100.,
                                       'evidence': 'NUMERICAL_TEST_ONLY'}]
            path = Path(root) / 'unmapped'
            with self.assertRaisesRegex(FloodModelError, 'UNMAPPED_NODE_FLOODING'):
                run_coupled(model, path)
            failure = json.loads((path / 'coupled-failure.json').read_text())
            self.assertGreater(failure['lastNetwork']['totals']['floodingM3'], 0)
            self.assertEqual(failure['lastSynchronizedMilliseconds'], 0)
            self.assertFalse((path / 'coupled-result.json').exists())
            self.assertTrue((path / 'exchange-ledger.jsonl').is_file())


if __name__ == '__main__':
    unittest.main()
