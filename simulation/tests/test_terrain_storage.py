"""경사 지형의 부분 침수 적분·분할 불변성과 입력 거부 확인."""
from copy import deepcopy
import math
import unittest

from waterleague_sim.engine.flood_errors import FloodModelError
from waterleague_sim.terrain.storage import stage_storage, triangle_storage


def slope():
    return {'verticesM': [[0., 0.], [2., 0.], [0., 2.]],
            'triangles': [[0, 1, 2]], 'elevationM': [0., 2., 0.]}


class TerrainStorageTests(unittest.TestCase):
    def test_analytical_partial_triangles_and_flat_bed(self):
        for area, heights, stage, expected in [
            (2., [0., 2., 0.], 1., (1.5, 5/6)),
            (3., [0., 1., 3.], .5, (.25, 1/24)),
            (3., [0., 1., 3.], 2., (2.5, 13/6)),
            (3., [0., 1., 3.], 1., (1., 1/3)),
            (3., [0., 1., 3.], 3., (3., 5.)),
            (2., [0., 2., 2.], 1., (.5, 1/6)),
            (5., [4., 4., 4.], 4., (0., 0.)),
            (5., [4., 4., 4.], 6., (5., 10.)),
            (5., [4., 4., 4.], 0., (0., 0.)),
        ]:
            with self.subTest(heights=heights, stage=stage):
                actual = triangle_storage(area, heights, stage)
                for a, b in zip(actual, expected):
                    self.assertAlmostEqual(a, b, places=13)

    def test_linear_subdivision_preserves_volume_and_area_without_mutation(self):
        original = slope()
        refined = {'verticesM': [*original['verticesM'], [1., 0.], [1., 1.], [0., 1.]],
                   'elevationM': [0., 2., 0., 1., 1., 0.],
                   'triangles': [[0, 3, 5], [3, 1, 4], [5, 4, 2], [3, 4, 5]]}
        before = deepcopy(refined)
        levels = [-1., 0., .01, .5, 1., 1.5, 2., 3.]
        a = stage_storage(original, [0], levels)
        b = stage_storage(refined, [0, 1, 2, 3], levels)
        self.assertEqual(before, refined)
        for left, right in zip(a['levels'], b['levels']):
            self.assertAlmostEqual(left['storageM3'], right['storageM3'], places=13)
            self.assertAlmostEqual(left['wettedPlanAreaM2'], right['wettedPlanAreaM2'], places=13)
            self.assertGreaterEqual(left['linearMinusCentroidStorageM3'], -1e-14)
        self.assertAlmostEqual(a['levels'][4]['storageM3'], 5/6)
        self.assertAlmostEqual(a['levels'][4]['centroidStorageM3'], 2/3)
        self.assertNotEqual(a['sourceGeometrySha256'], b['sourceGeometrySha256'])
        self.assertFalse(a['hydraulicConnectivityVerified'])

    def test_volume_derivative_translation_and_shallow_double_minimum(self):
        for heights in ([0., 1., 3.], [0., 0., 3.], [0., 3., 3.]):
            for stage in (.1, .5, 1.5, 2.9):
                area, volume = triangle_storage(7., heights, stage)
                step = 1e-5
                derivative = (triangle_storage(7., heights, stage+step)[1]
                              - triangle_storage(7., heights, stage-step)[1])/(2*step)
                self.assertAlmostEqual(area, derivative, places=8)
                shifted = triangle_storage(7., [z+10000 for z in heights], stage+10000)
                self.assertAlmostEqual(shifted[1], volume, places=10)
        area, volume = triangle_storage(2., [0., 0., 2.], 1e-10)
        self.assertGreater(volume, 0.)
        self.assertTrue(math.isclose(volume, 1e-20, rel_tol=1e-9))
        self.assertTrue(math.isclose(area, 2e-10, rel_tol=1e-9))

    def test_rejects_invalid_geometry_and_stages(self):
        for kind in ('clockwise', 'degenerate', 'nan', 'boolean', 'duplicate', 'nested', 'levels', 'large'):
            surface, cells, levels = slope(), [0], [1.]
            if kind == 'clockwise':
                surface['triangles'] = [[0, 2, 1]]
            elif kind == 'degenerate':
                surface['verticesM'][2] = [1., 0.]
            elif kind == 'nan':
                surface['elevationM'][0] = float('nan')
            elif kind == 'boolean':
                cells = [False]
            elif kind == 'duplicate':
                cells = [0, 0]
            elif kind == 'nested':
                cells = [[0]]
            elif kind == 'levels':
                levels = [1., 1.]
            else:
                levels = list(range(513))
            with self.subTest(kind=kind), self.assertRaises(FloodModelError):
                stage_storage(surface, cells, levels)


if __name__ == '__main__':
    unittest.main()
