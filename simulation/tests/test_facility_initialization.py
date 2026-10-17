"""합성 기상은 제원 변환·초기화 구간 수지 검증에만 사용."""
import copy
import tempfile
import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from test_continuous import model_for
from waterleague_sim.engine import continuous, facilities, initialization


class FacilityInitializationTests(unittest.TestCase):
    def test_public_soil_and_void_ratio_conversion_without_legacy_changes(self):
        model, placement = model_for('PERMEABLE_PAVEMENT', [1]*10)
        before = continuous.input_source(model, [placement], None)
        configured = copy.deepcopy(model)
        configured['facilityDesignSet'] = facilities.design_set()
        source = continuous.input_source(configured, [placement], None)
        self.assertIn('PP PAVEMENT 100 0.25 0 711.2 0', source)
        self.assertIn('PP STORAGE 300 0.5384615384615384', source)
        self.assertIn('RG SOIL 610 0.52 0.15 0.08 119.38 39.3 48.26', source)
        self.assertIn('GR SOIL 150 0.55 0.4 0.125 1016 40 75', source)
        self.assertEqual(before, continuous.input_source(model, [placement], None))
        configured['facilityDesignSet']['sha256'] = '0'*64
        with self.assertRaises(continuous.SimulationQualityError):
            continuous.input_source(configured, [placement], None)

    @unittest.skipUnless(continuous.library_path().exists(), 'EPA 연속 엔진 필요')
    def test_antecedent_weather_changes_initial_state_and_excludes_warmup_score(self):
        model, placement = model_for('GREEN_ROOF', [1]*120)
        model['facilityDesignSet'] = facilities.design_set()
        model['sharedSiteSource'] = {'inflowPolicy': 'DIRECT_RAINFALL_ONLY'}
        model['rainfall']['stationId'] = '108'
        model['rainfall']['sourceHashes'] = ['test-evaluation']
        start = datetime.fromisoformat(model['rainfall']['start'])
        pet = {'method': 'SYNTHETIC_TEST_ONLY', 'sourceHashes': ['test-pet'], 'ratesMmDay': [3]*120}
        prior = {'rainfall': {'start': (start-timedelta(days=7)).isoformat(), 'end': start.isoformat(),
            'stationId': '108', 'intervalSeconds': 60, 'sourceHashes': ['test-antecedent'],
            'depthsMm': [0]*(initialization.MINUTES-120)+[1]*120},
            'evaporation': pet | {'ratesMmDay': [3]*initialization.MINUTES}}
        expanded, full_pet = initialization.prepend(model, pet, prior)
        with tempfile.TemporaryDirectory() as directory:
            wet = continuous.experiment(expanded, placement, Path(directory)/'wet', full_pet)
            self.assertEqual(len(wet['contribution']), 120)
            self.assertEqual(wet['strategy']['initial']['at'], start.isoformat())
            self.assertGreater(wet['strategy']['initial']['soilMoisture'], .125)
            self.assertEqual(wet['strategy']['initial']['precipitationM3'], 0)
            expected_rain = model['cells'][0]['areaM2']*.12
            self.assertAlmostEqual(wet['strategy']['final']['precipitationM3'], expected_rain, delta=model['cells'][0]['areaM2']/60000*1.01)
            for run in ('baseline','strategy'):
                original = wet[run]['warmup']['final']
                self.assertEqual(wet[run]['initial']['storageM3'], original['storageM3'])
                self.assertLess(abs(wet[run]['final']['balanceResidualM3']), .01*expected_rain)
            self.assertAlmostEqual(sum(p['incrementM3'] for p in wet['contribution']), wet['contribution'][-1]['cumulativeM3'])
            prior['rainfall']['depthsMm'] = [0]*initialization.MINUTES
            dry_model, dry_pet = initialization.prepend(model, pet, prior)
            dry = continuous.experiment(dry_model, placement, Path(directory)/'dry', dry_pet)
            self.assertLess(dry['strategy']['initial']['soilMoisture'], wet['strategy']['initial']['soilMoisture'])
            self.assertNotEqual(dry['contribution'][-1]['cumulativeM3'], wet['contribution'][-1]['cumulativeM3'])
            prior['rainfall']['stationId'] = '999'
            with self.assertRaises(continuous.SimulationQualityError):
                initialization.prepend(model, pet, prior)


if __name__ == '__main__':
    unittest.main()
