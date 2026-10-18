"""시간 경계의 기준고·보간·물수지·결합 시각 검증."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from importlib.util import find_spec
import json
import hashlib
import math
from pathlib import Path
import tempfile
import unittest

from waterleague_sim.engine.flood_errors import FloodModelError
from waterleague_sim.engine.flood_process import EngineProcess
from waterleague_sim.engine.coupled_flood import run_coupled
from waterleague_sim.forcing.stage import StageSeries, require_stage_clock
from waterleague_sim.ingestion.wamis_stage import normalize, diagnostic_boundary, read_archive
from waterleague_sim.reference.flood_cases import mesh, coupled_limited_case

START = '2020-01-01T00:00:00+00:00'


def boundary(values, duration, datum='ANALYTICAL_ZERO'):
    start = datetime.fromisoformat(START)
    return {'type': 'TIME_SERIES_STAGE', 'unit': 'm', 'interpolation': 'LINEAR',
        'maximumGapSeconds': duration, 'momentum': 'ZERO_RESERVOIR_ASSUMPTION',
        'verticalDatum': datum, 'referenceStatus': 'LOCAL_DIAGNOSTIC',
        'evidence': 'NUMERICAL_TEST_ONLY_NOT_OBSERVED',
        'samples': [{'timeUtc': (start + timedelta(seconds=t)).isoformat(), 'stageM': value}
                    for t, value in values]}


class StageContractTests(unittest.TestCase):
    def test_interpolation_timezone_and_no_extrapolation(self):
        spec = boundary([(0, 1), (10, 2), (20, .5)], 20)
        model = {'startUtc': '2020-01-01T09:00:00+09:00', 'durationSeconds': 20,
                 'verticalDatum': 'ANALYTICAL_ZERO'}
        series = StageSeries(spec, model)
        self.assertEqual(series(5), [1.5, 0, 0])
        self.assertEqual(series(15), [1.25, 0, 0])
        self.assertEqual(series(20), [.5, 0, 0])
        self.assertEqual(series(math.nextafter(20., math.inf)), [.5, 0, 0])
        self.assertEqual(series.knots, (10,))
        for time in (-.001, 20.001):
            with self.assertRaisesRegex(FloodModelError, 'STAGE_TIME_OUTSIDE'):
                series(time)

    def test_absolute_datum_requires_source_and_historical_coverage(self):
        model = {'startUtc': START, 'durationSeconds': 20, 'verticalDatum': 'TEST_DATUM',
                 'terrainProvenance': {'absoluteVerticalReferenceVerified': True}}
        spec = boundary([(0, 1), (20, 2)], 20, 'TEST_DATUM') | {'referenceStatus': 'VERIFIED_ABSOLUTE'}
        with self.assertRaisesRegex(FloodModelError, 'DATUM_EVIDENCE_REQUIRED'):
            StageSeries(spec, model)
        proof = {'verticalDatum': 'TEST_DATUM', 'sourceSha256': 'a' * 64,
                 'validFromUtc': '2021-01-01T00:00:00Z', 'validUntilUtc': '2022-01-01T00:00:00Z'}
        with self.assertRaisesRegex(FloodModelError, 'DATUM_PERIOD_MISMATCH'):
            StageSeries(spec | {'datumEvidence': proof}, model)
        proof['validFromUtc'] = '2019-01-01T00:00:00Z'
        self.assertEqual(StageSeries(spec | {'datumEvidence': proof}, model)(10), [1.5, 0, 0])

    def test_missing_duplicate_gap_datum_and_timezone_are_rejected(self):
        model = {'startUtc': START, 'durationSeconds': 20, 'verticalDatum': 'ANALYTICAL_ZERO'}
        original = boundary([(0, 1), (10, 2), (20, .5)], 20)
        cases = [({'verticalDatum': 'OTHER'}, 'DATUM'), ({'maximumGapSeconds': 9}, 'GAP'),
                 ({'samples': original['samples'][1:]}, 'COVERAGE'),
                 ({'samples': original['samples'] + [original['samples'][-1]]}, 'ORDER'),
                 ({'samples': [original['samples'][0], {'timeUtc': START, 'stageM': None}]}, 'SAMPLE')]
        for change, code in cases:
            with self.subTest(code=code), self.assertRaisesRegex(FloodModelError, code):
                StageSeries(original | change, model)
        with self.assertRaisesRegex(FloodModelError, 'TIME_INVALID'):
            StageSeries(original, model | {'startUtc': '2020-01-01T00:00:00'})
        with self.assertRaisesRegex(FloodModelError, 'TERRAIN_DATUM_UNVERIFIED'):
            StageSeries(original, model | {'terrainProvenance': {'absoluteVerticalReferenceVerified': False}})

    def test_rain_and_network_clock_must_match_before_run(self):
        model = coupled_limited_case()
        surface = model['surface'] | {'startUtc': START, 'durationSeconds': 5}
        surface['boundaryConditions']['left'] = boundary([(0, 1.05), (5, 1.05)], 5)
        with self.assertRaisesRegex(FloodModelError, 'NETWORK_CLOCK_MISMATCH'):
            require_stage_clock(surface, duration=5, network=model['network'])
        require_stage_clock(surface, duration=5, network=model['network'] | {'timeZone': 'UTC'})
        with self.assertRaisesRegex(FloodModelError, 'RAIN_CLOCK_MISMATCH'):
            require_stage_clock(surface, duration=5, rainfall={'startUtc': START,
                                'endUtc': '2020-01-01T00:00:06Z'})

    def test_wamis_hour24_missing_and_negative_gauge_level(self):
        row = {'ymdh': '2022-08-08'} | {f'h{i}': str(i / 10) for i in range(1, 25)}
        row['h1'], row['h2'] = '-0.2', '-9999'
        result = normalize(json.dumps({'rows': [row], 'max': [{'wl': '999'}]}).encode(),
                           '1018662', '20220808', '20220808')
        self.assertEqual(result['missingCount'], 1)
        self.assertEqual(result['records'][0]['gaugeLevelM'], -.2)
        self.assertEqual(result['records'][-1]['timeUtc'], '2022-08-08T15:00:00+00:00')
        self.assertEqual(result['records'][-1]['gaugeLevelM'], 2.4)
        with self.assertRaisesRegex(FloodModelError, 'WINDOW_HAS_MISSING'):
            diagnostic_boundary(result, '2022-08-07T16:00:00Z', '2022-08-07T18:00:00Z')
        spec = diagnostic_boundary(result, '2022-08-08T09:00:00Z', '2022-08-08T15:00:00Z')
        self.assertEqual(spec['referenceStatus'], 'LOCAL_DIAGNOSTIC')
        self.assertEqual(spec['samples'][0]['stageM'], 1.8)
        with self.assertRaisesRegex(FloodModelError, 'DAY_MISSING'):
            normalize(b'{"rows":[]}', '1018662', '20220808', '20220808')

    def test_archive_rebuilds_original_and_rejects_changed_derived_values(self):
        raw = json.dumps({'rows': [{'ymdh': '2022-08-08'} | {f'h{i}': '2' for i in range(1, 25)}]}).encode()
        normalized = normalize(raw, '1018662', '20220808', '20220808')
        with tempfile.TemporaryDirectory() as root_name:
            root = Path(root_name)
            (root / 'hourly.json').write_bytes(raw)
            (root / 'normalized.json').write_text(json.dumps(normalized))
            def manifest():
                body = {'schemaVersion': 1, 'source': 'WAMIS_PUBLIC_HOURLY_TABLE',
                    'stationId': '1018662', 'parameters': {'date1': '20220808', 'date2': '20220808'},
                    'files': {name: hashlib.sha256((root / name).read_bytes()).hexdigest()
                              for name in ('hourly.json', 'normalized.json')}}
                value = json.dumps(body).encode()
                (root / 'manifest.json').write_bytes(value)
                return hashlib.sha256(value).hexdigest()
            expected = manifest()
            self.assertEqual(read_archive('manifest.json', expected, root)[0], normalized)
            normalized['records'][0]['gaugeLevelM'] = 3
            (root / 'normalized.json').write_text(json.dumps(normalized))
            with self.assertRaisesRegex(FloodModelError, 'SOURCE_HASH_MISMATCH'):
                read_archive('manifest.json', expected, root)
            with self.assertRaisesRegex(FloodModelError, 'NORMALIZATION_MISMATCH'):
                read_archive('manifest.json', manifest(), root)
            with self.assertRaisesRegex(FloodModelError, 'PATH_INVALID'):
                read_archive('../manifest.json', expected, root)


@unittest.skipUnless(find_spec('anuga'), 'flood 선택 의존성 설치 필요')
class StageNativeTests(unittest.TestCase):
    def test_constant_series_matches_fixed_boundary_and_lake(self):
        import numpy as np
        model = mesh(4, 2, 4, 2, water=lambda x, z: np.ones(len(x)))
        model.update(schemaVersion=2, maxStepSeconds=.1, startUtc=START, durationSeconds=10)
        outputs = []
        with tempfile.TemporaryDirectory() as root:
            for name, spec in [('fixed', {'type': 'FIXED_STAGE', 'stageM': 1}),
                               ('series', boundary([(0, 1), (10, 1)], 10))]:
                candidate = deepcopy(model)
                candidate['boundaryConditions']['left'] = spec
                with EngineProcess('surface', candidate, Path(root) / name) as session:
                    outputs.append(session.call('advance', 10))
                    result = session.call('finish')
                    self.assertEqual(result['numericalStatus'], 'PASSED')
            self.assertEqual(outputs[0], outputs[1])
            self.assertLess(abs(outputs[1]['balanceResidualM3']), 1e-10)
            self.assertEqual(result['stageBoundaries']['left']['extrapolation'], 'FORBIDDEN')
            self.assertIn('stageAdapterSha256', result['engine'])

    def test_rising_falling_boundary_and_replay(self):
        import numpy as np
        model = mesh(8, 2, 8, 2, water=lambda x, z: np.ones(len(x)))
        model.update(schemaVersion=2, maxStepSeconds=.05, startUtc=START, durationSeconds=30)
        model['boundaryConditions']['left'] = boundary([(0, 1), (10, 1.3), (20, .6), (30, .6)], 30)
        histories = []
        with tempfile.TemporaryDirectory() as root:
            for name in ('first', 'replay'):
                with EngineProcess('surface', model, Path(root) / name) as session:
                    history = [session.call('advance', 10) for _ in range(3)]
                    self.assertGreater(history[0]['storageM3'], 16)
                    self.assertLess(history[-1]['storageM3'], history[0]['storageM3'])
                    self.assertLess(abs(history[-1]['balanceResidualM3']), 1e-7)
                    self.assertEqual(session.call('finish')['numericalStatus'], 'PASSED')
                    histories.append(history)
            self.assertEqual(histories[0], histories[1])

    def test_coupled_frames_do_not_change_stage_physics(self):
        outcomes = []
        with tempfile.TemporaryDirectory() as root:
            for frame in (50, 1000):
                model = coupled_limited_case()
                model['network']['timeZone'] = 'UTC'
                model['surface'].update(schemaVersion=2, startUtc=START, durationSeconds=5)
                model['surface']['boundaryConditions']['left'] = boundary(
                    [(0, 1.05), (2.5, 1.06), (5, 1.05)], 5)
                model['frameIntervalMilliseconds'] = frame
                result = run_coupled(model, Path(root) / str(frame))
                self.assertEqual(result['numericalStatus'], 'PASSED')
                outcomes.append(result['balance'])
            self.assertEqual(outcomes[0], outcomes[1])


if __name__ == '__main__':
    unittest.main()
