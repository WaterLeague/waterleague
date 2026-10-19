import copy
import json
from pathlib import Path
import tempfile
import unittest

from shapely.geometry import MultiPolygon, Polygon, box, mapping

from waterleague_sim.engine import continuous, swmm
from waterleague_sim.engine.facilities import design_set
from waterleague_sim.spatial.geometry import dimensions
import test_continuous as fixtures


class SiteGeometryInputTests(unittest.TestCase):
    def model(self):
        model, placement = fixtures.model_for('GREEN_ROOF', [1] * 7)
        geometry = MultiPolygon([Polygon(box(0, 0, 10, 10).exterior.coords,
                                         [box(2, 2, 8, 8).exterior.coords]), box(20, 0, 22, 2)])
        model['cells'] = [{'id': 'SOURCE', 'kind': 'ROOF', 'geometry': mapping(geometry), 'geometryCrs': 'EPSG:5186', 'areaM2': 68,
            'maxAreaM2': 68, 'allowedTypes': ['GREEN_ROOF'],
            'physicalInputs': dimensions(geometry) | {'slopePercent': 1}}]
        model['sharedSiteSource'] = {'inflowPolicy': 'DIRECT_RAINFALL_ONLY'}
        model['facilityDesignSet'] = design_set(4)
        placement.update(cellId='SOURCE', areaM2=68)
        return model, placement

    def test_engine_rejects_hole_area_overcount_and_unrelated_width_before_execution(self):
        model, placement = self.model()
        original = copy.deepcopy(model)
        source = continuous.input_source(model, [placement], None)
        row = source.split('[SUBCATCHMENTS]\n')[1].splitlines()[0].split()
        self.assertAlmostEqual(float(row[3]) * 10000, 68)
        self.assertAlmostEqual(float(row[5]), 68 / 22)
        self.assertEqual(model, original)
        for field, value in [('areaM2', 104), ('maxAreaM2', 69), ('geometry', None),
                             ('physicalInputs', None), ('geometryCrs', 'EPSG:4326'), ('geometryCrs', None)]:
            invalid = copy.deepcopy(model)
            invalid['cells'][0][field] = value
            with self.subTest(field=field), self.assertRaises(swmm.SimulationQualityError):
                continuous.input_source(invalid, [placement], None)
        invalid = copy.deepcopy(model)
        invalid['cells'][0]['physicalInputs']['runoffWidthM'] = 10
        with self.assertRaises(swmm.SimulationQualityError):
            continuous.input_source(invalid, [placement], None)

    @unittest.skipUnless(continuous.library_path().exists(), '상태 관측 엔진 빌드 필요')
    def test_actual_epa_rain_volume_uses_holes_multipart_and_archived_geometry_code(self):
        model, placement = self.model()
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)
            result = continuous.experiment(model, placement, path)
            for key in ('baseline', 'strategy'):
                self.assertAlmostEqual(result[key]['final']['precipitationM3'], 68 * .007, delta=1e-6)
            self.assertAlmostEqual(result['strategy']['final']['lidInflowM3'], 68 * .007, delta=1e-6)
            manifest = json.loads((path / 'manifest.json').read_text())
            self.assertEqual(manifest['site_geometry.py'], result['strategy']['engine']['geometryAdapterSha256'])
            self.assertEqual((path / 'site_geometry.py').read_bytes(),
                (continuous.ROOT / 'simulation/waterleague_sim/spatial/geometry.py').read_bytes())


if __name__ == '__main__':
    unittest.main()
