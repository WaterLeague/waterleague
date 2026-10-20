"""해석해가 있는 표면·중복 자료·외삽·높이 기준의 파생 계약 검사."""
from copy import deepcopy
import unittest

from waterleague_sim.engine.coupled_flood import _validate
from waterleague_sim.engine.flood_errors import FloodModelError
from waterleague_sim.reference.flood_cases import coupled_case
from waterleague_sim.terrain.contours import ContourTin, controls, surface_from_contours


def point(identifier, xy, z):
    return {'id': identifier, 'role': 'ELEVATION_POINT', 'scaleDenominator': 1000,
        'geometry': {'type': 'Point', 'coordinates': list(xy)}, 'attributes': {'수치': str(z)},
        'sourceShapeSha256': '1'*64, 'sourceDbfSha256': '2'*64, 'spatialCatalogSha256': '3'*64}


def plane():
    return [point(str(i), [200000.+x, 540000.+y], 2*x-3*y-5)
            for i, (x, y) in enumerate([(0, 0), (20, 0), (0, 20), (20, 20), (10, 10)])]


def grid(tin):
    return tin.grid([200000., 540000., 200020., 540020.], 10., {'source.json': '0'*64},
        {'unit': 'm', 'unitStatus': 'PRODUCT_FAMILY_INFERRED', 'datum': None,
         'datumVerified': False, 'unitEvidence': 'SYNTHETIC_TEST'})


def specification():
    return {'manningN': [.01]*8, 'initialDepthM': [0.]*8, 'rainfallOwner': ['SURFACE']*8,
        'maxStepSeconds': 1.,
        'boundaryConditions': {k: {'type': 'TRANSMISSIVE'} for k in ('north', 'south', 'east', 'west')},
        'evidence': {k: 'SYNTHETIC_TEST' for k in ('roughness', 'initialState', 'rainfallOwner', 'boundary')}}


class ContourTerrainTests(unittest.TestCase):
    def test_affine_surface_exact_negative_elevations_and_boundary(self):
        rows = plane()
        original = deepcopy(rows)
        tin = ContourTin(rows)
        for x, y in [(0, 0), (20, 20), (3.3, 7.8), (0, 6.2), (13., 9.)]:
            sample = tin.sample([200000.+x, 540000.+y])
            self.assertAlmostEqual(sample['heightM'], 2*x-3*y-5, places=8)
            self.assertAlmostEqual(sum(sample['weights']), 1., places=15)
        self.assertIsNone(tin.sample([199999.999999, 540010.]))
        self.assertEqual(rows, original)
        self.assertEqual(tin.identity, ContourTin(list(reversed(rows))).identity)

    def test_coincident_sources_kept_but_conflicting_elevation_rejected(self):
        rows = plane()+[point('duplicate', [200000., 540000.], -5)]
        parsed = controls(rows)
        self.assertEqual(len(parsed), 5)
        self.assertEqual(next(r for r in parsed if r['xy'] == [200000., 540000.])['recordIndexes'], [0, 5])
        rows[-1]['attributes']['수치'] = '-5.01'
        with self.assertRaisesRegex(FloodModelError, 'HEIGHT_CONFLICT'):
            ContourTin(rows)

    def test_contour_vertices_and_spot_heights_share_one_interpolator(self):
        rows = [point('bottom', [0., 0.], 0.), point('top', [0., 10.], 10.)]
        for i, row in enumerate(rows):
            row.update(role='CONTOUR_LINE', attributes={'등고수치': str(i*10.)},
                geometry={'type': 'LineString', 'coordinates': [[0., i*10.], [10., i*10.]]})
        rows.append(point('middle', [5., 5.], 5.))
        tin = ContourTin(rows)
        self.assertAlmostEqual(tin.sample([8., 4.])['heightM'], 4., places=12)
        self.assertTrue(tin.describe()['contourEdgesConstrained'])

    def test_contour_refinement_preserves_segment_instead_of_cutting_through_it(self):
        row = point('contour', [0., 0.], 0.)
        row.update(role='CONTOUR_LINE', attributes={'등고수치': '0'},
                   geometry={'type': 'LineString', 'coordinates': [[0., 0.], [10., 0.]]})
        tin = ContourTin([row, point('upper', [5., 1.], 10.), point('lower', [5., -1.], 10.)])
        self.assertGreater(len(tin.points), tin.original_point_count)
        self.assertEqual(tin.refinement[-1]['missingContourEdges'], 0)
        for x in (.3, 1.7, 4.1, 5.5, 9.9):
            self.assertAlmostEqual(tin.sample([x, 0.])['heightM'], 0., places=10)
        self.assertTrue(any(p['derivedFromSegments'] for p in tin.points))

    def test_invalid_source_geometry_missing_and_nonfinite_height_rejected(self):
        changes = [('attributes', {'수치': 'NaN'}), ('attributes', {'수치': None}),
                   ('geometry', {'type': 'Point', 'coordinates': [1., 2., 3.]}),
                   ('scaleDenominator', 5000), ('sourceDbfSha256', 'bad')]
        for key, value in changes:
            with self.subTest(key=key, value=value):
                rows = plane()
                rows[0][key] = value
                with self.assertRaises(FloodModelError):
                    ContourTin(rows)
        with self.assertRaisesRegex(FloodModelError, 'RECORD_INVALID'):
            ContourTin(plane()+[plane()[0]])

    def test_grid_origin_order_and_height_are_exact(self):
        derived = grid(ContourTin(plane()))
        surface = surface_from_contours(derived, specification())
        self.assertEqual(surface['terrainProvenance']['originProjected'], [200000., 540020.])
        self.assertEqual(surface['elevationM'], [2*x-3*y-5 for y in (20, 10, 0) for x in (0, 10, 20)])
        self.assertEqual(len(surface['triangles']), 8)
        self.assertNotEqual(surface['terrainProvenance']['sampling'], 'ORIGINAL_PIXEL_CENTERS_NO_RESAMPLING')
        self.assertFalse(surface['terrainProvenance']['absoluteVerticalReferenceVerified'])

    def test_no_grid_extrapolation_or_fractional_boundary(self):
        tin = ContourTin(plane())
        for bounds, code in [([199990., 540000., 200020., 540020.], 'OUTSIDE_SUPPORT'),
                             ([200000., 540000., 200019., 540020.], 'DIMENSIONS_INVALID')]:
            with self.assertRaisesRegex(FloodModelError, code):
                tin.grid(bounds, 10., {'source.json': '0'*64}, {})

    def test_unverified_datum_cannot_bypass_existing_coupling_guard(self):
        model = coupled_case()
        model['surface'] = surface_from_contours(grid(ContourTin(plane())), specification())
        for key in ('coordinateSystem', 'verticalDatum'):
            model['network'][key] = model['surface'][key]
        with self.assertRaisesRegex(FloodModelError, 'VERTICAL_REFERENCE_UNVERIFIED'):
            _validate(model)


if __name__ == '__main__':
    unittest.main()
