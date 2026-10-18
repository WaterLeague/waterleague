"""면적 교차·혼합 토양의 중복 차감·미확보 입력 검사."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
from pyproj import CRS
from shapely.geometry import Polygon, box, mapping

from waterleague_sim.engine.coupled_flood import run_coupled
from waterleague_sim.engine.flood_errors import FloodModelError
from waterleague_sim.engine.flood_process import EngineProcess
from waterleague_sim.engine.surface_infiltration import validate
from waterleague_sim.forcing.surface_run import run_observed_surface
from waterleague_sim.reference.flood_cases import mesh
from waterleague_sim.terrain.coverage import (PolygonLayer, assign, infiltration_from_assignment,
                                             mesh_polygons, projection)
from test_observed_surface_rainfall import observed_coupled, specification


def layer(geometries):
    return PolygonLayer([{'id': str(i), 'properties': {'label': 'TEST'}, 'geometry': mapping(g)}
                         for i, g in enumerate(geometries)], lambda x, y: (x, y), {'evidence': 'NUMERICAL_TEST'})


def mixed(model, *, conductivity=36., deficit=0.):
    cells = [i for i, owner in enumerate(model['rainfallOwner']) if owner == 'SURFACE']
    return {'schemaVersion': 2, 'method': 'GREEN_AMPT', 'ownershipPolicy': 'SURFACE_ONLY',
        'partitionPolicy': 'EXPLICIT_AREA_FRACTIONS', 'initialization': 'EPA_INITIAL_DEFICIT_SEED',
        'recoveryFactor': 1., 'evidence': 'NUMERICAL_TEST_ONLY',
        'imperviousRegions': [{'triangles': cells, 'areaFraction': .3, 'evidence': 'TEST'}],
        'regions': [{'triangles': cells, 'perviousFraction': f, 'suctionMm': 100.,
                     'conductivityMmH': conductivity * k, 'initialMoistureDeficit': deficit,
                     'evidence': 'TEST'} for f, k in ((.3, 1), (.4, 2))]}


class CoverageTests(unittest.TestCase):
    def test_holes_boundary_touch_and_overlap_never_inflate_area(self):
        hole = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)],
                       holes=[[(2, 2), (4, 2), (4, 4), (2, 4)]])
        source = layer([hole, box(5, 0, 10, 10), box(10, 0, 12, 10)])
        report, parts = source.measure(box(0, 0, 10, 10))
        self.assertEqual(report['coveredValidAreaM2'], 96.)
        self.assertEqual(report['gapAreaM2'], 4.)
        self.assertEqual(report['overlapAreaM2'], 50.)
        self.assertEqual(report['exclusiveAreaM2'], 46.)
        self.assertEqual(report['unresolvedAreaM2'], 54.)
        self.assertEqual(len(report['intersections']), 2)
        self.assertEqual(len(parts), 1)

    def test_invalid_geometry_is_not_repaired_or_hidden_by_other_polygon(self):
        invalid = Polygon([(2, 2), (4, 4), (2, 4), (4, 2), (2, 2)])
        source = layer([box(0, 0, 10, 10), invalid])
        report, _ = source.measure(box(0, 0, 10, 10))
        self.assertEqual(report['invalidEnvelopeAffectedAreaM2'], 4.)
        self.assertEqual(report['exclusiveAreaM2'], 96.)
        self.assertEqual(report['invalidFeatureIds'], ['1'])
        self.assertEqual(len(source.invalid), 1)

    def test_joint_assignment_and_explicit_parameters_compile_without_average(self):
        model = mesh(1, 1, 10, 10, water=lambda x, z: x * 0 + .02)
        soil = layer([box(0, 0, 5, 10), box(5, 0, 10, 10)])
        cover = layer([box(0, 0, 10, 10)])
        report = assign(model, soil, cover)
        self.assertEqual(report['totals']['jointAreaM2'], 100.)
        self.assertEqual(report['totals']['jointUnresolvedAreaM2'], 0.)
        params = {str(i): {'suctionMm': 100., 'conductivityMmH': k, 'evidence': 'TEST'}
                  for i, k in enumerate((3., 30.))}
        initialization = {'initialMoistureDeficit': 0., 'recoveryFactor': 1., 'evidence': 'TEST'}
        with self.assertRaisesRegex(FloodModelError, 'SURFACE_MATERIAL_REQUIRED'):
            infiltration_from_assignment(model, report, params, {}, initialization=initialization)
        spec = infiltration_from_assignment(model, report, params,
            {'0': {'perviousFraction': .7, 'evidence': 'EXPLICIT_TEST_MATERIAL'}}, initialization=initialization)
        self.assertEqual(len(spec['regions']), 4)
        self.assertEqual({r['conductivityMmH'] for r in spec['regions']}, {3., 30.})
        for cell in range(2):
            self.assertAlmostEqual(sum(r['perviousFraction'] for r in spec['regions']
                                       if cell in r['triangles']), .7)
        self.assertEqual(report, assign(model, soil, cover))
        changed = deepcopy(model); changed['rainfallOwner'][0] = 'NETWORK'
        with self.assertRaisesRegex(FloodModelError, 'ASSIGNMENT_INVALID'):
            infiltration_from_assignment(changed, report, params, {}, initialization=initialization)
        model.update(schemaVersion=2, infiltration=spec)
        with tempfile.TemporaryDirectory() as temporary:
            with EngineProcess('surface', model, Path(temporary) / 'compiled') as engine:
                final = engine.call('advance', 60)
                engine.call('finish')
        self.assertAlmostEqual(final['infiltrationM3'], .01925, places=10)
        self.assertAlmostEqual(final['storageM3'], 1.98075, places=10)

    def test_spatial_gap_and_duplicate_mesh_rejected(self):
        model = mesh(1, 1)
        report = assign(model, layer([box(0, 0, 5, 10)]), layer([box(0, 0, 10, 10)]))
        with self.assertRaisesRegex(FloodModelError, 'SPATIAL_ASSIGNMENT_INCOMPLETE'):
            infiltration_from_assignment(model, report, {}, {}, initialization={'evidence': 'TEST'})
        model['triangles'].append(model['triangles'][0])
        with self.assertRaisesRegex(FloodModelError, 'MESH_OVERLAP'):
            mesh_polygons(model)

    def test_projection_keeps_source_crs_and_local_origin(self):
        wkt = CRS.from_epsg(5186).to_wkt()
        convert, evidence = projection(wkt, wkt, [200_000., 550_000.], [127., 37., 128., 38.])
        x, y = convert([200_002., 200_003.], [550_004., 550_005.])
        np.testing.assert_array_equal(x, [2., 3.])
        np.testing.assert_array_equal(y, [4., 5.])
        self.assertFalse(evidence['allowBallpark'])
        self.assertEqual(evidence['targetWkt'], wkt)


class MixedInfiltrationTests(unittest.TestCase):
    def test_overlap_gap_and_network_ownership_rejected(self):
        model = mesh(1, 1)
        spec = mixed(model)
        for delta, code in ((.1, 'AREA_OVERLAP'), (-.1, 'COVERAGE_INCOMPLETE')):
            bad = deepcopy(spec); bad['regions'][0]['perviousFraction'] += delta
            with self.assertRaisesRegex(FloodModelError, code):
                validate(bad, model['rainfallOwner'])
        model['rainfallOwner'][0] = 'NETWORK'
        with self.assertRaisesRegex(FloodModelError, 'DOUBLE_COUNT'):
            validate(spec, model['rainfallOwner'])

    def test_mixed_saturated_area_integration_state_and_replay(self):
        model = mesh(1, 1, water=lambda x, z: x * 0 + .02)
        model.update(schemaVersion=2, infiltration=mixed(model))
        results = []
        with tempfile.TemporaryDirectory() as temporary:
            for name, segments in [('whole', [60]), ('replay', [60]), ('segmented', [10] * 6)]:
                directory = Path(temporary) / name
                with EngineProcess('surface', model, directory) as engine:
                    for dt in segments:
                        final = engine.call('advance', dt)
                    result = engine.call('finish')
                self.assertAlmostEqual(final['infiltrationM3'], .066, places=10)
                self.assertAlmostEqual(final['storageM3'], 1.934, places=10)
                self.assertLess(abs(final['balanceResidualM3']), 1e-9)
                self.assertEqual(result['numericalStatus'], 'PASSED')
                state = json.loads((directory / 'surface-infiltration.json').read_text())
                self.assertEqual(state['triangles'], [0, 1, 0, 1])
                self.assertEqual(len(state['nativeState']), 4)
                self.assertEqual(state['effectivePerviousAreaM2'], 70.)
                self.assertAlmostEqual(sum(state['infiltrationByPatchM3']), final['infiltrationM3'], places=12)
                self.assertAlmostEqual(sum(r['infiltrationM3'] for r in state['triangleTotals']), .066, places=10)
                self.assertNotIn('infiltrationByTriangleM3', state)
                results.append(final)
            self.assertEqual(results[0], results[1])
            np.testing.assert_allclose(results[0]['depthM'], results[2]['depthM'], atol=1e-12)

    def test_multiple_dry_patches_cannot_infiltrate_more_than_actual_rain(self):
        model = mesh(1, 1)
        spec = mixed(model, conductivity=1000, deficit=.3)
        spec['imperviousRegions'] = []
        for row in spec['regions']:
            row['perviousFraction'] = .5
        model.update(schemaVersion=2, infiltration=spec)
        with tempfile.TemporaryDirectory() as temporary:
            result = run_observed_surface(model, specification(model, end='2022-08-08T09:02:00Z'),
                                          Path(temporary) / 'rain')
        self.assertAlmostEqual(result['final']['rainfallM3'], .15, places=10)
        self.assertAlmostEqual(result['final']['infiltrationM3'], .15, places=10)
        self.assertAlmostEqual(result['final']['storageM3'], 0., places=10)
        self.assertEqual(result['numericalStatus'], 'PASSED')

    def test_explicitly_all_impervious_has_zero_soil_states_and_losses(self):
        model = mesh(1, 1, water=lambda x, z: x * 0 + .02)
        spec = mixed(model)
        spec['regions'] = []
        spec['imperviousRegions'][0]['areaFraction'] = 1.
        model.update(schemaVersion=2, infiltration=spec)
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / 'sealed'
            with EngineProcess('surface', model, directory) as engine:
                final = engine.call('advance', 60)
                engine.call('finish')
            state = json.loads((directory / 'surface-infiltration.json').read_text())
        self.assertAlmostEqual(final['storageM3'], 2., places=12)
        self.assertEqual(final['infiltrationM3'], 0.)
        self.assertEqual(state['nativeState'], [])

    def test_mixed_soils_coupled_ledger_excludes_network_owned_rain(self):
        model = observed_coupled()
        surface = model['surface']
        surface.update(schemaVersion=2, infiltration=mixed(surface, conductivity=3.302, deficit=.3))
        with tempfile.TemporaryDirectory() as temporary:
            result = run_coupled(model, Path(temporary) / 'coupled')
        balance = result['balance']
        self.assertGreater(balance['surfaceInfiltrationM3'], 0.)
        self.assertAlmostEqual(balance['surfaceRainfallM3'] - balance['surfaceInfiltrationM3']
            + balance['surfaceBoundaryNetInflowM3'], balance['surfaceExternalNetInflowM3'], places=9)
        self.assertLess(abs(balance['exchangeCancellationResidualM3']), 1e-8)
        self.assertEqual(result['numericalStatus'], 'PASSED')


if __name__ == '__main__':
    unittest.main()
