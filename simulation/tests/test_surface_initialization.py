"""선행 원문 재산정·평가 구간 분리·상태 비초기화 검사."""
from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from waterleague_sim.engine.flood_errors import FloodModelError
from waterleague_sim.forcing.antecedent_archive import read_antecedent
from waterleague_sim.forcing.observed_rainfall import RainfallSchedule
from waterleague_sim.forcing.surface_initialization import prepare_initialized_surface
from waterleague_sim.forcing.surface_run import run_schedule
from waterleague_sim.reference.flood_cases import mesh

ROOT = Path(__file__).resolve().parents[2]
REFERENCE = {'file': 'seoul-20220808-421-14d-v1.json.gz',
             'sha256': '95c290cbbaaee551c73e3f24795605945bcc4d978b2b6c225392f5aef1f7fe98'}
RELATIVE = 'data/derived/surface-antecedent/' + REFERENCE['file']


class AntecedentArchiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rain, cls.pet, cls.files, cls.summary = read_antecedent(REFERENCE)

    def test_real_raw_rain_weather_reconstruction_and_portable_archive(self):
        self.assertEqual(len(self.rain['depthsMm']), 20160)
        self.assertAlmostEqual(sum(self.rain['depthsMm']), 239.)
        self.assertEqual(len(self.pet['ratesMmDay']), 20160)
        archived_rates = json.loads(gzip.decompress(self.files[RELATIVE]))['evaporation']['ratesMmDay']
        self.assertEqual(self.pet['ratesMmDay'], archived_rates)
        self.assertEqual([v for part in self.pet['segments'] for v in part['ratesMmDay']], archived_rates)
        self.assertTrue(self.summary['qualityWarnings'])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name, raw in self.files.items():
                path = root/name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(raw)
            actual = read_antecedent(REFERENCE, root)
            self.assertEqual(actual[0], self.rain)
            self.assertEqual(actual[1], self.pet)

    def test_rehashed_derived_values_and_raw_missing_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name, raw in self.files.items():
                path = root/name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(raw)
            for field, values, error in [('rainfall', 'depthsMm', 'RAIN_DERIVATION_MISMATCH'),
                                          ('evaporation', 'ratesMmDay', 'WEATHER_DERIVATION_MISMATCH')]:
                original = json.loads(gzip.decompress(self.files[RELATIVE]))
                original[field][values][0] += .1
                raw = gzip.compress(json.dumps(original).encode(), mtime=0)
                (root/RELATIVE).write_bytes(raw)
                with self.assertRaisesRegex(FloodModelError, error):
                    read_antecedent(REFERENCE | {'sha256': hashlib.sha256(raw).hexdigest()}, root)
            (root/RELATIVE).write_bytes(self.files[RELATIVE])
            (root/self.rain['sourceRequests'][0]['rawFile']).unlink()
            with self.assertRaisesRegex(FloodModelError, 'SOURCE_INVALID'):
                read_antecedent(REFERENCE, root)

    def test_unsafe_reference_and_changed_archive_hash_rejected(self):
        with self.assertRaisesRegex(FloodModelError, 'REFERENCE_INVALID'):
            read_antecedent(REFERENCE | {'file': '../outside.json.gz'})
        with self.assertRaisesRegex(FloodModelError, 'SOURCE_HASH_MISMATCH'):
            read_antecedent(REFERENCE | {'sha256': '0'*64})


class SurfaceInitializationTests(unittest.TestCase):
    def test_same_continuous_solution_with_readonly_evaluation_state(self):
        model = mesh(1, 1, 10, 10)
        model.update(schemaVersion=2, maxStepSeconds=1.)
        model['infiltration'] = {'schemaVersion': 1, 'method': 'GREEN_AMPT', 'ownershipPolicy': 'SURFACE_ONLY',
            'initialization': 'EPA_INITIAL_DEFICIT_SEED', 'recoveryFactor': 1., 'imperviousTriangles': [],
            'evidence': 'NUMERICAL_TEST_ONLY', 'regions': [{'triangles': [0, 1], 'perviousFraction': 1.,
                'suctionMm': 88.9, 'conductivityMmH': 3.302, 'initialMoistureDeficit': .25,
                'evidence': 'NUMERICAL_TEST_ONLY'}]}
        spec = {'stationByTriangle': ['421', '421']}
        schedule = RainfallSchedule([
            {'timeMilliseconds': 0, 'ratesMmHByStation': {'421': 60.}},
            {'timeMilliseconds': 60000, 'ratesMmHByStation': {'421': 120.}}],
            {'durationSeconds': 120, 'expectedSurfaceRainfallM3': .3,
             'evaluationRainfall': {'expectedSurfaceRainfallM3': .2}}, {})
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            a = run_schedule(model, spec, schedule, root/'continuous')
            b = run_schedule(model, spec, schedule, root/'with-evaluation', evaluation_start=60)
            self.assertEqual(a['final'], b['final'])
            state = json.loads((root/'with-evaluation/evaluation-initial-state.json').read_bytes())
            self.assertGreater(state['infiltration']['infiltrationM3'], 0)
            self.assertGreater(state['infiltration']['nativeState'][0][1], 0)
            ledger = b['initialization']['evaluationLedger']
            self.assertAlmostEqual(ledger['rainfallM3'], .2)
            self.assertAlmostEqual(ledger['balanceResidualM3'], 0., places=12)
            self.assertEqual(ledger['initialStorageM3'], state['surface']['storageM3'])
            self.assertEqual(ledger['durationSeconds'], 60)
            self.assertTrue(b['initialization']['scoreExcludesWarmup'])

    def test_actual_period_binding_and_metrics_shift_preserve_original(self):
        import sys
        sys.path.insert(0, str(ROOT/'scripts'))
        from verify_surface_initialization import inputs
        model, spec, initialization = inputs({'suctionMm': 88.9, 'conductivityRangeMmH': [3.302, 10.922]})
        model['evaluationMetrics'] = {'startMilliseconds': 0, 'endMilliseconds': 359*60*1000}
        original = deepcopy(model)
        value, combined, schedule, seconds = prepare_initialized_surface(model, spec, initialization | {'days': 7})
        self.assertEqual(model, original)
        self.assertEqual(seconds, 604800)
        self.assertEqual(value['evaluationMetrics']['startMilliseconds'], seconds*1000)
        self.assertEqual(value['evaluationMetrics']['endMilliseconds'], (seconds+359*60)*1000)
        self.assertEqual(schedule.summary['evaluationRainfall']['expectedSurfaceRainfallM3'], 8.5)
        self.assertEqual(combined['evaluationStartUtc'], spec['startUtc'])
        with self.assertRaisesRegex(FloodModelError, 'RAIN_BINDING_INVALID'):
            prepare_initialized_surface(model, spec, initialization | {'days': 28})
        with self.assertRaisesRegex(FloodModelError, 'WEATHER_BINDING_INVALID'):
            prepare_initialized_surface(model, spec, initialization | {'weatherReference': {'file': 'unbound'}})


if __name__ == '__main__':
    unittest.main()
