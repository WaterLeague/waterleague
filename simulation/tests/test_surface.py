"""해석해·정수면·강우 체적으로 확인하는 2D 수치 시험. 서울 관측이 아님."""
import copy
from importlib.util import find_spec
from pathlib import Path
import tempfile
import unittest

from waterleague_sim.engine.flood_errors import FloodModelError
from waterleague_sim.engine.flood_process import EngineProcess
from waterleague_sim.reference.flood_cases import mesh


@unittest.skipUnless(find_spec('anuga'), 'flood 선택 의존성 설치 필요')
class SurfaceTests(unittest.TestCase):
    def test_lake_at_rest_over_nonflat_bed(self):
        import numpy as np
        model = mesh(bed=lambda x, y: .3 * np.sin(x / 20 * np.pi), water=lambda x, z: 1 - z)
        with tempfile.TemporaryDirectory() as root:
            with EngineProcess('surface', model, Path(root) / 'lake') as session:
                result = session.call('advance', 30)
                self.assertLess(max(abs(v) for v in result['velocityXMps'] + result['velocityYMps']), 1e-9)
                np.testing.assert_allclose(result['depthM'], model['initialDepthM'], atol=1e-10, rtol=0)
                self.assertLess(abs(result['balanceResidualM3']), 1e-8)
                self.assertEqual(session.call('finish')['numericalStatus'], 'PASSED')

    def test_rainfall_volume_no_double_input_and_segmented_replay(self):
        import numpy as np
        model = mesh()
        n = len(model['triangles'])
        model['rainfallOwner'][:n//2] = ['NETWORK'] * (n//2)
        rain = [0.] * (n//2) + [60.] * (n - n//2)
        with tempfile.TemporaryDirectory() as root:
            with EngineProcess('surface', model, Path(root) / 'invalid-rain') as session:
                with self.assertRaisesRegex(FloodModelError, 'DOUBLE_COUNT'):
                    session.call('set_rainfall', [60.] * n)
            with EngineProcess('surface', model, Path(root) / 'rain') as session:
                session.call('set_rainfall', rain)
                for _ in range(6):
                    result = session.call('advance', 10)
                self.assertAlmostEqual(result['sourceNetInflowM3'], .05, places=10)
                self.assertAlmostEqual(result['storageM3'], .05, places=8)
                session.call('finish')
            with EngineProcess('surface', model, Path(root) / 'replay') as replay:
                replay.call('set_rainfall', rain)
                for _ in range(6):
                    replay_result = replay.call('advance', 10)
                self.assertEqual(replay_result, result)
                replay.call('finish')
            with EngineProcess('surface', model, Path(root) / 'full') as full:
                full.call('set_rainfall', rain)
                full_result = full.call('advance', 60)
                np.testing.assert_allclose(full_result['depthM'], result['depthM'], atol=2e-5, rtol=0)
                full.call('finish')

    def test_dry_dam_break_moves_water_and_improves_with_mesh_refinement(self):
        import numpy as np
        errors = []
        with tempfile.TemporaryDirectory() as root:
            for nx in (100, 200):
                model = mesh(nx, 5, 200, 10, water=lambda x, z: (x < 100).astype(float))
                with EngineProcess('surface', model, Path(root) / str(nx)) as session:
                    result = session.call('advance', 5)
                    points, triangles = np.asarray(model['verticesM']), np.asarray(model['triangles'])
                    x = points[triangles, 0].mean(axis=1) - 100
                    gravity = session.info['gravityMps2']
                    c = np.sqrt(gravity)
                    exact = np.where(x < -5*c, 1, np.where(x > 10*c, 0, (2*c - x/5)**2 / (9*gravity)))
                    errors.append(float(np.mean(abs(np.asarray(result['depthM']) - exact))))
                    self.assertLess(abs(result['balanceResidualM3']), 1e-7)
                    self.assertGreater(max(result['velocityXMps']), 1)
                    self.assertGreater(np.max(np.asarray(result['depthM'])[x > 10]), .02)
                    self.assertEqual(session.call('finish')['numericalStatus'], 'PASSED')
            self.assertLess(errors[1], .01)
            self.assertLess(errors[1], errors[0])

    def test_missing_boundary_and_invalid_geometry_fail_closed(self):
        model = mesh()
        with tempfile.TemporaryDirectory() as root:
            missing = copy.deepcopy(model)
            missing['boundaryEdges'].pop()
            with self.assertRaisesRegex(FloodModelError, 'BOUNDARY_INCOMPLETE'):
                with EngineProcess('surface', missing, Path(root) / 'missing'):
                    pass
            invalid = copy.deepcopy(model)
            invalid['triangles'][0].reverse()
            with self.assertRaisesRegex(FloodModelError, 'TRIANGLE_INVALID'):
                with EngineProcess('surface', invalid, Path(root) / 'invalid'):
                    pass
