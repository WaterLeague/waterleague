"""원본 격자 중심·높이·경계·출처와 기준고 미확인 결합 거부 검사."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from pyproj import CRS

from waterleague_sim.engine.coupled_flood import run_coupled
from waterleague_sim.engine.flood_errors import FloodModelError
from waterleague_sim.reference.flood_cases import coupled_case
from waterleague_sim.terrain.grid import surface_from_grid


def inputs():
    grid = {'schemaVersion': 1, 'width': 3, 'height': 2,
        'coordinateWkt': CRS.from_epsg(5186).to_wkt(),
        'geoTransform': [200000., 90., 0., 550000., 0., -90.],
        'values': [11., 12., 13., 14., 15., 16.], 'noDataValue': -9999,
        'sourceFiles': {'fixture.img': '0'*64}, 'sourcePixelWindow': [0, 0, 3, 2],
        'verticalReference': {'unit': 'm', 'unitStatus': 'PRODUCT_FAMILY_INFERRED',
                             'unitEvidence': 'NUMERICAL_TEST', 'datum': None, 'datumVerified': False}}
    spec = {'manningN': [.03]*4, 'initialDepthM': [0.]*4, 'rainfallOwner': ['SURFACE']*4,
            'maxStepSeconds': .1,
            'boundaryConditions': {side: {'type': 'TRANSMISSIVE'}
                                   for side in ('north', 'south', 'east', 'west')},
            'evidence': {key: 'NUMERICAL_TEST' for key in ('roughness', 'initialState', 'boundary', 'rainfallOwner')}}
    return grid, spec


class TerrainGridTests(unittest.TestCase):
    def test_native_centers_heights_and_complete_counterclockwise_boundary(self):
        grid, spec = inputs()
        original = deepcopy((grid, spec))
        model = surface_from_grid(grid, spec)
        self.assertEqual((grid, spec), original)
        self.assertEqual(model['elevationM'], grid['values'])
        self.assertEqual(model['terrainProvenance']['originProjected'], [200045., 549955.])
        self.assertEqual(model['verticesM'], [[0., 0.], [90., 0.], [180., 0.],
                                            [0., -90.], [90., -90.], [180., -90.]])
        edges, area = {}, 0.
        for index, tri in enumerate(model['triangles']):
            a, b, c = [model['verticesM'][i] for i in tri]
            cross = (b[0]-a[0])*(c[1]-a[1]) - (b[1]-a[1])*(c[0]-a[0])
            self.assertGreater(cross, 0)
            area += cross/2
            for k in range(3):
                edges.setdefault(tuple(sorted((tri[(k+1)%3], tri[(k+2)%3]))), []).append((index, k))
        self.assertEqual(area, 180*90)
        self.assertEqual({(i, k) for i, k, _ in model['boundaryEdges']},
                         {positions[0] for positions in edges.values() if len(positions) == 1})
        self.assertEqual(model, surface_from_grid(grid, spec))
        self.assertFalse(model['rankingEligible'])

    def test_nodata_and_nonfinite_values_are_never_filled(self):
        for value in (-9999., None, float('nan'), float('inf')):
            grid, spec = inputs()
            grid['values'][2] = value
            with self.assertRaisesRegex(FloodModelError, 'HEIGHT_MISSING'):
                surface_from_grid(grid, spec)

    def test_no_implicit_units_projection_or_hydraulic_fields(self):
        cases = [('verticalReference', None, 'VERTICAL_REFERENCE'),
                 ('coordinateWkt', CRS.from_epsg(4326).to_wkt(), 'METRIC_PROJECTION'),
                 ('coordinateWkt', 'invalid wkt', 'COORDINATE_REFERENCE'),
                 ('geoTransform', [0., 90., 1., 0., 0., -90.], 'TRANSFORM_INVALID')]
        for field, value, error in cases:
            grid, spec = inputs()
            grid[field] = value
            with self.assertRaisesRegex(FloodModelError, error):
                surface_from_grid(grid, spec)
        for field, error in [('manningN', 'HYDRAULIC_FIELDS'), ('evidence', 'FIELD_EVIDENCE'),
                             ('boundaryConditions', 'BOUNDARY_REQUIRED'), ('rainfallOwner', 'RAIN_OWNER')]:
            grid, spec = inputs()
            spec.pop(field)
            with self.assertRaisesRegex(FloodModelError, error):
                surface_from_grid(grid, spec)

    def test_source_or_grid_changes_change_provenance_identity(self):
        grid, spec = inputs()
        baseline = surface_from_grid(grid, spec)
        grid['sourceFiles']['fixture.img'] = '1'*64
        updated = surface_from_grid(grid, spec)
        self.assertNotEqual(baseline['terrainProvenance']['gridSha256'], updated['terrainProvenance']['gridSha256'])
        grid['geoTransform'][0] += 90
        moved = surface_from_grid(grid, spec)
        self.assertNotEqual(updated['coordinateSystem'], moved['coordinateSystem'])

    def test_unverified_vertical_origin_cannot_enter_network_coupling(self):
        model = coupled_case()
        model['surface'] = surface_from_grid(*inputs())
        for key in ('coordinateSystem', 'verticalDatum'):
            model['network'][key] = model['surface'][key]
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)/'coupled'
            with self.assertRaisesRegex(FloodModelError, 'VERTICAL_REFERENCE_UNVERIFIED'):
                run_coupled(model, output)
            self.assertFalse(output.exists())

    def test_confirmed_datum_requires_source_unit_evidence(self):
        grid, spec = inputs()
        grid['verticalReference'].update(datum='INCHON_1916', datumVerified=True)
        inferred = surface_from_grid(grid, spec)
        self.assertFalse(inferred['terrainProvenance']['absoluteVerticalReferenceVerified'])
        grid['verticalReference']['unitStatus'] = 'SOURCE_CONFIRMED'
        confirmed = surface_from_grid(grid, spec)
        self.assertTrue(confirmed['terrainProvenance']['absoluteVerticalReferenceVerified'])
        self.assertEqual(confirmed['verticalDatum'], 'INCHON_1916')
