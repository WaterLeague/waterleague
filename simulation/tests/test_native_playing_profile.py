import copy
import json
from pathlib import Path
import tempfile
import unittest

from shapely.geometry import MultiPolygon, Polygon, box, mapping

from waterleague_sim.engine import continuous, facilities
from waterleague_sim.spatial import design_footprint, playing_profile, reference_conditions
from waterleague_sim.spatial.geometry import SiteGeometryError
import test_continuous as fixtures


def cell(kind='GROUND', role='CULTIVATION_LANDSCAPE_AREA', geometry=None):
    geometry = geometry if geometry is not None else box(200000, 550000, 200020, 550010)
    return {'id': 'C0123456789abcdef01234567', 'kind': kind, 'role': role,
        'sourceObjectId': 'ngii:TEST_ONLY', 'geometry': mapping(geometry), 'geometryCrs': 'EPSG:5186',
        'areaM2': geometry.area, 'maxAreaM2': geometry.area}


def configured(source, properties):
    profile = playing_profile.bind(source, properties)
    model, _ = fixtures.model_for('GREEN_ROOF', [1] * 30 + [0] * 30)
    model.update(cells=[source | profile], hydrology=playing_profile.hydrology(),
        facilityDesignSet=facilities.design_set(4), sharedSiteSource={'inflowPolicy': 'DIRECT_RAINFALL_ONLY'})
    return model


class NativePlayingProfileTests(unittest.TestCase):
    def test_public_unit_conversions_and_missing_field_values_remain_separate(self):
        value = reference_conditions.catalog()
        self.assertEqual(value['soilScenario']['conductivityMmH'], .13 * 25.4)
        self.assertAlmostEqual(value['soilScenario']['suctionMm'], 3.5 * 25.4)
        self.assertAlmostEqual(value['soilScenario']['initialMoistureDeficit'], .463 - .232)
        self.assertIsNone(value['soilScenario']['fieldSoilClassification'])
        profile = playing_profile.bind(cell(), {'구분': '밭'})
        p = profile['physicalInputs']
        self.assertEqual(p['soilStatus'], reference_conditions.SOIL_STATUS)
        self.assertEqual(p['localSoilStatus'], 'UNRESOLVED')
        self.assertEqual(p['localSlopeStatus'], 'UNRESOLVED')
        self.assertEqual(profile['siteEligibility'], 'UNKNOWN')
        self.assertEqual(p['imperviousPercent'], 0)

    def test_roles_do_not_turn_farmland_into_pavement_or_paddy_into_dry_soil(self):
        road = playing_profile.bind(cell(role='ROAD_AREA'), {})
        self.assertEqual(road['allowedTypes'], ['PERMEABLE_PAVEMENT'])
        self.assertEqual(road['physicalInputs']['imperviousPercent'], 100)
        roof = playing_profile.bind(cell('ROOF', 'BUILDING_FOOTPRINT'), {'층수': '4'})
        self.assertEqual(roof['allowedTypes'], ['GREEN_ROOF'])
        self.assertEqual(roof['heightM'], 12.8)
        for value in ('논', '조림지', None, '미분류'):
            profile = playing_profile.bind(cell(), {'구분': value})
            self.assertEqual(profile['status'], 'UNSUPPORTED_SURFACE_PROCESS')
            self.assertEqual(profile['allowedTypes'], [])

    def test_fixed_width_design_stays_in_one_component_and_avoids_every_hole(self):
        first = Polygon(box(200000, 550000, 200020, 550020).exterior.coords,
                        [box(200005, 550005, 200015, 550015).exterior.coords])
        geometry = MultiPolygon([first, box(200100, 550000, 200110, 550010)])
        source = cell(geometry=geometry)
        before = copy.deepcopy(source)
        profile = playing_profile.bind(source, {'구분': '목초지'})
        for name in ('swaleDesign', 'trenchDesign'):
            design = profile['physicalInputs'][name]
            polygon = Polygon(design['coordinates'])
            self.assertTrue(first.covers(polygon))
            design_footprint.validate(source, design)
            invalid = copy.deepcopy(design)
            invalid['center'][0] += 1
            with self.assertRaises(SiteGeometryError):
                design_footprint.validate(source, invalid)
            invalid = copy.deepcopy(design)
            invalid['maxLengthM'] = 0
            with self.assertRaises(SiteGeometryError):
                design_footprint.validate(source, invalid)
        self.assertEqual(source, before)

    def test_narrow_source_excludes_wide_design_and_keeps_other_supported_facilities(self):
        source = cell(geometry=box(200000, 550000, 200000.5, 550010))
        profile = playing_profile.bind(source, {'구분': '밭'})
        self.assertEqual(profile['allowedTypes'], ['RAIN_GARDEN', 'BIORETENTION'])

    def test_reference_values_cannot_be_relabelled_as_local_measurements_or_arbitrary_rates(self):
        model = configured(cell(), {'구분': '밭'})
        for key, value in [('conductivityMmH', 30), ('imperviousPercent', 100),
                           ('referenceScenario', {'id': 'bad', 'sha256': 'a' * 64})]:
            invalid = copy.deepcopy(model)
            invalid['cells'][0]['physicalInputs'][key] = value
            with self.assertRaises(continuous.SimulationQualityError):
                continuous.input_source(invalid, [], None)
        self.assertEqual(model['cells'][0]['physicalInputs']['rainGardenBoundary']['basis'], reference_conditions.BASIS)
        invalid = copy.deepcopy(model)
        physical = invalid['cells'][0]['physicalInputs']
        physical.update(reference_conditions.catalog()['surfaceScenarios']['PAVEMENT_REFERENCE'])
        physical['surfaceScenarioId'] = 'PAVEMENT_REFERENCE'
        with self.assertRaises(continuous.SimulationQualityError):
            continuous.input_source(invalid, [], None)

    def test_source_writes_pervious_baseline_and_public_conditions_to_the_engine(self):
        model = configured(cell(), {'구분': '밭'})
        source = continuous.input_source(model, [], None)
        rows = source.split('[SUBCATCHMENTS]\n')[1].splitlines()[0].split()
        self.assertEqual(float(rows[4]), 0)
        rows = source.split('[SUBAREAS]\n')[1].splitlines()[0].split()
        self.assertEqual([float(v) for v in rows[1:5]], [.012, .06, 1.27, 2.54])
        rows = source.split('[INFILTRATION]\n')[1].splitlines()[0].split()
        self.assertEqual([float(v) for v in rows[1:4]], [88.9, 3.302, .231])

    @unittest.skipUnless(continuous.library_path().exists(), 'EPA 상태 관측 엔진 필요')
    def test_all_six_facilities_use_one_engine_and_archive_the_reference_dependencies(self):
        cases = [(cell('ROOF', 'BUILDING_FOOTPRINT'), {'층수': '4'}),
                 (cell(role='ROAD_AREA'), {}), (cell(), {'구분': '밭'})]
        tested = set()
        with tempfile.TemporaryDirectory() as temporary:
            for original, properties in cases:
                model = configured(original, properties)
                for facility in model['cells'][0]['allowedTypes']:
                    maximum = model['cells'][0]['maxAreaM2']
                    if facility in ('VEGETATIVE_SWALE', 'INFILTRATION_TRENCH'):
                        key = 'swaleDesign' if facility == 'VEGETATIVE_SWALE' else 'trenchDesign'
                        maximum = model['cells'][0]['physicalInputs'][key]['maxAreaM2']
                    placement = {'cellId': original['id'], 'facilityType': facility, 'areaM2': maximum}
                    result = continuous.experiment(model, placement, Path(temporary) / facility)
                    self.assertAlmostEqual(result['strategy']['final']['lidInflowM3'], maximum * .03, delta=1e-5)
                    manifest = json.loads((Path(temporary) / facility / 'manifest.json').read_text())
                    engine = result['strategy']['engine']
                    self.assertEqual(manifest['reference_conditions.py'], engine['referenceConditionsAdapterSha256'])
                    self.assertEqual(manifest['reference-surfaces.json'], engine['referenceScenarioSha256'])
                    self.assertEqual(manifest['design_footprint.py'], engine['designFootprintAdapterSha256'])
                    tested.add(facility)
        self.assertEqual(tested, set(playing_profile.FACILITY_ORDER))


if __name__ == '__main__':
    unittest.main()
