"""내부 단계 원 지표의 평가 창·영역·방향·프레임 독립성 검증."""
from importlib.util import find_spec
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from waterleague_sim.engine.coupled_flood import run_coupled
from waterleague_sim.engine.flood_errors import FloodModelError
from waterleague_sim.engine.flood_metrics import DepthMetrics, validate_metrics
from waterleague_sim.engine.flood_process import EngineProcess
from waterleague_sim.engine.network_metrics import library_path
from waterleague_sim.reference.flood_cases import coupled_case, coupled_limited_case, mesh


def specification(count, *, start=0, end=5000):
    return {'schemaVersion': 1, 'policyVersion': 'NUMERICAL_TEST_ONLY_v1',
            'evidence': 'NUMERICAL_TEST_EXPOSURE_NOT_SEOUL',
            'startMilliseconds': start, 'endMilliseconds': end,
            'networkOutfalls': ['OUT'], 'exposureTriangles': list(range(count)),
            'wetDepthThresholdM': .001}


@unittest.skipUnless(find_spec('numpy'), '수치 배열 의존성 필요')
class DepthMetricTests(unittest.TestCase):
    def test_clipped_linear_integral_excludes_unselected_area_and_spinup(self):
        import numpy as np
        state = {'time': 0.}
        stage = np.array([0., 10.])
        domain = SimpleNamespace(areas=np.array([2., 3.]),
            quantities={'stage': SimpleNamespace(centroid_values=stage),
                        'elevation': SimpleNamespace(centroid_values=np.zeros(2))},
            get_time=lambda: state['time'], get_timestep=lambda: 1.,
            set_fractional_step_operator=lambda _: None)
        spec = specification(1, start=500, end=1500) | {'wetDepthThresholdM': .08}
        observer = DepthMetrics(domain, spec)
        stage[:] = [.1, 50.]
        observer()
        state['time'] = 1.
        stage[:] = [.2, 100.]
        observer()
        result = observer.snapshot()
        self.assertTrue(result['complete'])
        self.assertAlmostEqual(result['depthAreaTimeM3Hours'], .2 / 3600, places=14)
        self.assertAlmostEqual(result['maximumDepthM'], .15, places=14)
        self.assertAlmostEqual(result['wetDurationSeconds'][0], .7, places=14)
        self.assertEqual(result['maximumWetAreaM2'], 2)
        self.assertEqual(result['exposureAreaM2'], 2)
        self.assertEqual(stage.tolist(), [.2, 100.])

    def test_instant_exchange_adds_no_fictitious_duration_and_validates_clock(self):
        import numpy as np
        state = {'time': 0.}
        stage = np.array([0.])
        domain = SimpleNamespace(areas=np.array([1.]),
            quantities={'stage': SimpleNamespace(centroid_values=stage),
                        'elevation': SimpleNamespace(centroid_values=np.zeros(1))},
            get_time=lambda: state['time'], get_timestep=lambda: 1.,
            set_fractional_step_operator=lambda _: None)
        observer = DepthMetrics(domain, specification(1, end=1000))
        stage[:] = .2
        observer.reset_at_instant()
        self.assertEqual(observer.snapshot()['depthAreaTimeM3Hours'], 0)
        observer()
        self.assertAlmostEqual(observer.snapshot()['depthAreaTimeM3Hours'], .2 / 3600, places=14)
        state['time'] = 2
        with self.assertRaisesRegex(FloodModelError, 'CLOCK_MISMATCH'):
            observer.reset_at_instant()

    def test_missing_or_duplicate_exposure_and_invalid_windows_rejected(self):
        base = specification(2)
        for changes in ({'exposureTriangles': None}, {'exposureTriangles': [0, 0]},
                        {'exposureTriangles': [[1]]}, {'exposureTriangles': [True]},
                        {'endMilliseconds': 6000}, {'startMilliseconds': -1},
                        {'wetDepthThresholdM': float('nan')}, {'networkOutfalls': []}):
            with self.assertRaises(FloodModelError):
                validate_metrics(base | changes, 2, 5)
        validate_metrics(base | {'exposureTriangles': []}, 2, 5)


@unittest.skipUnless(find_spec('anuga') and library_path().exists(), '원 지표 엔진 설치 필요')
class FloodMetricEngineTests(unittest.TestCase):
    def test_constant_rain_analytical_depth_area_time_and_spinup(self):
        with tempfile.TemporaryDirectory() as root:
            model = mesh(2, 2, 2., 2.)
            model['maxStepSeconds'] = .1
            # 60mm/h의 선형 수심 증가에서 [1.25, 4.75]초만 평가한다.
            model['evaluationMetrics'] = specification(len(model['triangles']), start=1250, end=4750)
            with EngineProcess('surface', model, Path(root) / 'rain') as surface:
                surface.call('set_rainfall', [60.] * len(model['triangles']))
                surface.call('advance', 5)
                result = surface.call('finish')
            metrics = result['evaluationMetrics']
            expected = 4 * (60 / 3_600_000) * (4.75 ** 2 - 1.25 ** 2) / 2 / 3600
            self.assertAlmostEqual(metrics['depthAreaTimeM3Hours'], expected, places=14)
            self.assertTrue(metrics['complete'])
            self.assertGreater(metrics['nativeSteps'], 30)
            self.assertEqual(result['numericalStatus'], 'PASSED')

    def test_metrics_and_output_frames_do_not_change_engine_states(self):
        with tempfile.TemporaryDirectory() as root:
            reference = None
            measured = None
            for index, frame in enumerate((None, 50, 1000)):
                model = coupled_limited_case()
                if frame is not None:
                    model['frameIntervalMilliseconds'] = frame
                    model['evaluationMetrics'] = specification(len(model['surface']['triangles']),
                                                               start=1250, end=4750)
                path = Path(root) / str(index)
                result = run_coupled(model, path)
                n = json.loads((path / 'network/network-result.json').read_text())
                s = json.loads((path / 'surface/surface-result.json').read_text())
                physics = (result['balance'], result['steps'], n['final'], s['final'])
                if reference is None:
                    reference = physics
                else:
                    self.assertEqual(physics, reference)
                    metrics = result['evaluationMetrics']
                    self.assertTrue(metrics['complete'])
                    self.assertFalse(metrics['rankingEligible'])
                    if measured is None:
                        measured = metrics
                    else:
                        self.assertEqual(metrics, measured)
                    self.assertGreater(metrics['surface']['depthAreaTimeM3Hours'], 0)

    def test_outfall_volume_matches_ledger_and_internal_port_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            model = coupled_case()
            model['durationSeconds'] = 5
            model['evaluationMetrics'] = specification(len(model['surface']['triangles']))
            path = Path(root) / 'full'
            result = run_coupled(model, path)
            n = json.loads((path / 'network/network-result.json').read_text())
            metrics = result['evaluationMetrics']['network']
            self.assertAlmostEqual(metrics['combined']['outwardVolumeM3'],
                                   n['final']['nodes']['OUT']['boundaryOutflowM3'], places=12)
            self.assertGreater(metrics['combined']['nativeSteps'], result['steps'])
            self.assertGreater(metrics['combined']['peakOutwardM3s'], 0)
            model['evaluationMetrics']['networkOutfalls'] = ['SURFACE']
            with self.assertRaisesRegex(FloodModelError, 'EXTERNAL_OUTFALL_REQUIRED'):
                run_coupled(model, Path(root) / 'internal')

    def test_simultaneous_outfall_peak_is_not_sum_of_separate_peaks(self):
        with tempfile.TemporaryDirectory() as root:
            model = coupled_case()
            model['durationSeconds'] = 10
            inp = model['network']['inputText']
            inp = inp.replace('[OUTFALLS]', 'TANK2 0 5 0 FUNCTIONAL 0 0 1 0 0\n[OUTFALLS]')
            inp = inp.replace('OUT 0 FIXED 0 NO', 'OUT 0 FIXED 0 NO\nOUT2 0 FIXED 0 NO')
            inp = inp.replace('[ORIFICES]', '[ORIFICES]\nDRAIN2 TANK2 OUT2 BOTTOM 0 0.65 NO 0')
            inp = inp.replace('[XSECTIONS]', '[XSECTIONS]\nDRAIN2 CIRCULAR 0.1 0 0 0')
            model['network']['inputText'] = inp
            model['networkForcing'] = [{'timeMilliseconds': 5000, 'node': 'TANK2', 'flowM3s': .5,
                                        'evidence': 'NUMERICAL_TEST_ONLY'}]
            model['evaluationMetrics'] = specification(len(model['surface']['triangles']), end=10000)
            model['evaluationMetrics']['networkOutfalls'] = ['OUT', 'OUT2']
            result = run_coupled(model, Path(root) / 'two-outfalls')
            metrics = result['evaluationMetrics']['network']
            peak_sum = sum(row['peakOutwardM3s'] for row in metrics['outfalls'].values())
            self.assertLess(metrics['combined']['peakOutwardM3s'], peak_sum - 1e-5)
            self.assertAlmostEqual(metrics['combined']['outwardVolumeM3'],
                sum(row['outwardVolumeM3'] for row in metrics['outfalls'].values()), places=12)

    def test_failed_network_retains_raw_metrics_without_ranking(self):
        with tempfile.TemporaryDirectory() as root:
            model = coupled_case(conduit=True)
            model['evaluationMetrics'] = specification(len(model['surface']['triangles']), end=120000)
            result = run_coupled(model, Path(root) / 'failed')
            self.assertEqual(result['evaluationMetrics']['status'], 'FAILED_DIAGNOSTIC')
            self.assertTrue(result['evaluationMetrics']['complete'])
            self.assertFalse(result['evaluationMetrics']['rankingEligible'])
            self.assertGreater(result['evaluationMetrics']['raw']['outwardVolumeM3'], 0)

    def test_reverse_boundary_flow_is_not_counted_as_outflow(self):
        with tempfile.TemporaryDirectory() as root:
            model = coupled_case(initial_network=0)
            model['durationSeconds'] = 5
            model['network']['inputText'] = model['network']['inputText'].replace('OUT 0 FIXED 0 NO',
                                                                                  'OUT 0 FIXED 2 NO')
            model['evaluationMetrics'] = specification(len(model['surface']['triangles']))
            path = Path(root) / 'reverse'
            result = run_coupled(model, path)
            metrics = result['evaluationMetrics']['network']['combined']
            n = json.loads((path / 'network/network-result.json').read_text())
            self.assertGreater(metrics['inwardVolumeM3'], 0)
            self.assertGreater(metrics['peakInwardM3s'], 0)
            self.assertEqual(metrics['outwardVolumeM3'], 0)
            self.assertEqual(metrics['peakOutwardM3s'], 0)
            self.assertAlmostEqual(metrics['inwardVolumeM3'],
                                   n['final']['nodes']['OUT']['boundaryInflowM3'], places=12)

    def test_partial_native_network_window_matches_boundary_volume_difference(self):
        with tempfile.TemporaryDirectory() as root:
            model = coupled_case()
            model['network']['ports'] = model['ports']
            model['network']['evaluationMetrics'] = specification(len(model['surface']['triangles']),
                                                                 start=1250, end=4750)
            with EngineProcess('network_metrics', model['network'], Path(root) / 'partial',
                               evaluation_seconds=5) as network:
                initial = None
                for i in range(1, 501):
                    network.call('exchange_step', 10, {'inlet': 1.})
                    if i in (125, 475):
                        volume = network.call('snapshot')['nodes']['OUT']['boundaryOutflowM3']
                        if i == 125:
                            initial = volume
                        else:
                            expected = volume - initial
                result = network.call('finish')['evaluationMetrics']
                self.assertTrue(result['complete'])
                self.assertAlmostEqual(result['combined']['outwardVolumeM3'], expected, places=12)
                self.assertAlmostEqual(result['combined']['coveredSeconds'], 3.5, places=10)


if __name__ == '__main__':
    unittest.main()
