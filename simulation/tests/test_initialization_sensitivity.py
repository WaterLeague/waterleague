"""초기 상태 경계와 평가 구간의 수치 검증. 합성 입력은 운영 자료와 분리."""
import copy
import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from test_continuous import model_for
from waterleague_sim.engine import continuous, facilities, initialization
from waterleague_sim.engine import initialization_sensitivity as study


def inputs():
    model, placement = model_for('GREEN_ROOF', [1]*10)
    model['facilityDesignSet'] = facilities.design_set()
    model['sharedSiteSource'] = {'inflowPolicy': 'DIRECT_RAINFALL_ONLY'}
    model['rainfall'].update(stationId='108', sourceHashes=['SYNTHETIC_TEST_ONLY'])
    start = datetime.fromisoformat(model['rainfall']['start'])
    pet = {'method': 'SYNTHETIC_TEST_ONLY', 'sourceHashes': ['test-weather'], 'ratesMmDay': [0]*10}
    prior = {'rainfall': {'start': (start-timedelta(days=14)).isoformat(), 'end': start.isoformat(),
             'stationId': '108', 'intervalSeconds': 60, 'sourceHashes': ['test-rain'],
             'depthsMm': [0]*20160, 'depthMethods': ['DAILY_DIFFERENCE']*20160},
             'evaporation': pet | {'ratesMmDay': [0]*20160}}
    return model, placement, pet, prior


class InitializationSensitivityTests(unittest.TestCase):
    def test_trims_only_prior_window_and_keeps_input_immutable(self):
        model, _, pet, prior = inputs()
        start = datetime.fromisoformat(model['rainfall']['start'])-timedelta(days=7)
        prior['rainfall']['aggregatedRainIntervals'] = [
            {'start': (start-timedelta(minutes=1)).isoformat(), 'end': (start+timedelta(minutes=1)).isoformat(),
             'minutes': 2, 'totalMm': .4, 'timeDistribution': 'UNIFORM_NOT_MINUTE_OBSERVATIONS'}]
        before = copy.deepcopy(prior)
        shorter = study.window(prior, 7)
        self.assertEqual(shorter['rainfall']['aggregatedRainIntervals'][0]['minutes'], 1)
        self.assertEqual(shorter['rainfall']['aggregatedRainIntervals'][0]['totalMm'], .2)
        dry, _ = initialization.prepend(model, pet, shorter)
        wet, _ = initialization.prepend(model, pet, prior, warmup_minutes=20160, seed_percent=100)
        self.assertEqual(dry['initialization']['method'], initialization.METHOD)
        self.assertNotIn('seedSaturationPercent', dry['initialization'])
        self.assertEqual(wet['hydrology']['initialSaturationPercent'], 100)
        self.assertEqual(prior, before)
        with self.assertRaises(continuous.SimulationQualityError):
            study.window(prior, 28)
        with self.assertRaises(continuous.SimulationQualityError):
            initialization.prepend(model, pet, shorter, seed_percent=True)

    def test_failed_scenario_never_becomes_zero_or_a_successful_range(self):
        model, placement, pet, prior = inputs()
        with tempfile.TemporaryDirectory() as root, patch.object(continuous, 'replay', side_effect=continuous.SimulationQualityError('LIVE_NUMERICAL_QUALITY_FAILED')):
            report = study.analyze(model, placement, pet, prior, Path(root))
            self.assertEqual(report['comparison']['status'], 'INCOMPLETE')
            self.assertIsNone(report['comparison']['ranges'])
            self.assertTrue(all(c['status'] == 'FAILED' for c in report['cases']))

    @unittest.skipUnless(continuous.library_path().exists(), 'EPA 연속 엔진 필요')
    def test_native_dry_wet_states_evaluation_only_and_nonzero_seed_influence(self):
        model, placement, pet, prior = inputs()
        with tempfile.TemporaryDirectory() as root:
            report = study.analyze(model, placement, pet, prior, Path(root), days=(7,))
            self.assertTrue(all(c['status'] == 'SUCCEEDED' for c in report['cases']))
            dry, wet = report['cases']
            self.assertEqual(dry['initialization']['evaluationStart'], model['rainfall']['start'])
            self.assertEqual(dry['initialization']['warmupRainMm'], 0)
            self.assertGreater(wet['metrics']['initialSoilMoisture'], dry['metrics']['initialSoilMoisture'])
            self.assertGreater(report['comparison']['ranges']['initialStorageM3']['span'], 0)
            self.assertNotEqual(wet['metrics']['contributionM3'], dry['metrics']['contributionM3'])
            self.assertTrue(dry['initialization']['scoreExcludesWarmup'])
            for case in report['cases']:
                trace = json.loads((Path(root)/(case['label']+'.json')).read_bytes())
                final = trace['final']
                self.assertLessEqual(abs(case['evaluationBalanceResidualM3']),
                                     .01*(final['precipitationM3']+final['initialStorageM3']))
                self.assertEqual(len(trace['samples']), len(model['rainfall']['depthsMm']))
                expected_rain = model['cells'][0]['areaM2']*.01
                self.assertAlmostEqual(final['precipitationM3'], expected_rain, delta=expected_rain*1e-6)

    def test_evaluation_water_balance_failure_is_rejected(self):
        invalid = {'initial': {}, 'final': {'precipitationM3': 100, 'initialStorageM3': 20,
                                           'balanceResidualM3': 1.21}}
        with self.assertRaisesRegex(continuous.SimulationQualityError, 'SPINUP_EVALUATION_BALANCE_FAILED'):
            study.measures(invalid, invalid)


if __name__ == '__main__':
    unittest.main()
