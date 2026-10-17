"""격자 반경·내부 단계 수지·긴 실제 강우의 회귀 검사."""
from importlib.util import find_spec
import json
import math
from pathlib import Path
import tempfile
import unittest

from waterleague_sim.engine.flood_errors import FloodModelError
from waterleague_sim.engine.flood_process import EngineProcess
from waterleague_sim.engine.coupled_flood import run_coupled
from waterleague_sim.forcing.surface_run import run_observed_surface
from waterleague_sim.reference.flood_cases import mesh, coupled_limited_case
from test_observed_surface_rainfall import specification


@unittest.skipUnless(find_spec('anuga'), 'flood 선택 의존성 설치 필요')
class SurfaceQualityTests(unittest.TestCase):
    def test_new_radius_is_geometric_incircle_and_legacy_input_is_preserved(self):
        model = mesh(2, 2)
        with tempfile.TemporaryDirectory() as temporary:
            results = []
            for version in (1, 2):
                with EngineProcess('surface', model | {'schemaVersion': version},
                                   Path(temporary) / str(version)) as session:
                    session.call('advance', 1)
                    results.append(session.call('finish'))
            old, new = [r['numericalConfiguration'] for r in results]
            self.assertEqual(old['meshRadiusMethod'], 'CENTROID_TO_NEAREST_EDGE_MIDPOINT')
            self.assertEqual(new['meshRadiusMethod'], 'INSCRIBED_CIRCLE_2_AREA_OVER_PERIMETER')
            self.assertAlmostEqual(new['minimumRadiusM'], (10 + 2.5 - math.hypot(10, 2.5)) / 2, places=12)
            self.assertGreater(old['minimumRadiusM'], new['maximumRadiusM'])
            self.assertEqual(old['cfl'], new['cfl'])
            self.assertEqual(results[0]['final'], results[1]['final'])
            self.assertEqual(results[1]['numericalQuality']['nativeSteps'], 1)

    def test_observed_359_minutes_keep_water_with_correct_radius_and_larger_maximum_step(self):
        model = mesh(2, 2) | {'schemaVersion': 2, 'maxStepSeconds': 30.}
        with tempfile.TemporaryDirectory() as temporary:
            result = run_observed_surface(model, specification(model, stations=2), Path(temporary) / 'rain')
            self.assertEqual(result['numericalStatus'], 'PASSED')
            self.assertEqual(result['numericalQuality']['status'], 'PASSED')
            self.assertAlmostEqual(result['final']['storageM3'], 18.675, places=8)
            self.assertEqual(result['numericalQuality']['lastInternalTimeSeconds'], 21540)
            self.assertLess(result['numericalQuality']['maximumAbsoluteResidualM3'], 1e-8)
            self.assertGreater(result['numericalQuality']['nativeSteps'], 359)
            self.assertLess(result['numericalQuality']['nativeSteps'], 215400)

    def test_quality_observation_does_not_mutate_state_and_retains_native_failure(self):
        import numpy as np
        from waterleague_sim.engine.surface import SurfaceSession
        from waterleague_sim.engine.surface_quality import SurfaceQuality
        model = mesh(2, 2)
        model['maxStepSeconds'] = 30.
        with tempfile.TemporaryDirectory() as temporary:
            session = SurfaceSession(model, Path(temporary) / 'legacy-diagnostic')
            observer = SurfaceQuality(session.domain, session.initial_volume, session.directory)
            quantities = ['stage', 'xmomentum', 'ymomentum']
            before = [session.domain.quantities[key].centroid_values.copy() for key in quantities]
            observer.observe(0)
            for key, saved in zip(quantities, before):
                np.testing.assert_array_equal(session.domain.quantities[key].centroid_values, saved)
            session.set_rainfall([30. if i % 2 == 0 else 0. for i in range(8)])
            with self.assertRaisesRegex(FloodModelError, 'SURFACE_NATIVE_BALANCE_FAILED'):
                session.advance(120)
            evidence = json.loads((session.directory / 'surface-quality.json').read_bytes())
            self.assertEqual(evidence['status'], 'FAILED')
            self.assertGreater(evidence['nativeSteps'], 0)
            self.assertLess(evidence['lastInternalTimeSeconds'], 120)
            self.assertGreater(evidence['maximumAbsoluteResidualM3'], 1e-4)

    def test_coupled_exchange_is_included_in_native_quality_and_frames_do_not_change_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            outputs = []
            for index, frame in enumerate((50, 1000)):
                model = coupled_limited_case()
                model['surface']['schemaVersion'] = 2
                model['frameIntervalMilliseconds'] = frame
                result = run_coupled(model, Path(temporary) / str(index))
                self.assertEqual(result['numericalStatus'], 'PASSED')
                self.assertEqual(result['surfaceNumericalQuality']['status'], 'PASSED')
                self.assertGreater(result['balance']['surfaceToNetworkM3'], 0)
                outputs.append((result['balance'], result['surfaceNumericalQuality']))
            self.assertEqual(outputs[0], outputs[1])

    def test_unknown_surface_input_version_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            for version in (True, 3):
                with self.assertRaisesRegex(FloodModelError, 'REFERENCE_REQUIRED'):
                    with EngineProcess('surface', mesh(2, 2) | {'schemaVersion': version},
                                       Path(temporary) / str(version)):
                        pass
