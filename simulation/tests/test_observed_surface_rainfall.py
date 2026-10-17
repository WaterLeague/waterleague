"""실제 저장 강우의 품질·시간·공간 소유권 및 엔진 체적 연결 검사."""
from importlib.util import find_spec
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from waterleague_sim.engine.coupled_flood import run_coupled
from waterleague_sim.engine.flood_errors import FloodModelError
from waterleague_sim.engine.flood_process import EngineProcess
from waterleague_sim.forcing.observed_rainfall import compile_rainfall, read_station
from waterleague_sim.forcing.surface_run import run_observed_surface
from waterleague_sim.reference.flood_cases import mesh, coupled_case

REFERENCES = [
    {'file': 'kma-421-202208081800-202208082359-disaster-v1.json',
     'sha256': '21d21033308e31deafe9190f5a0723fded9e43562a0d7c5573cc94c3e99efd96'},
    {'file': 'kma-401-202208081800-202208082359-disaster-v1.json',
     'sha256': '39ce4686facc74c09f13c2911162ea0293a30a8cac410da821a5fa51a423f21c'}]


def specification(model, *, end='2022-08-08T14:59:00+00:00', stations=1):
    return {'schemaVersion': 1, 'startUtc': '2022-08-08T09:00:00+00:00', 'endUtc': end,
            'assignmentEvidence': '실제 관측의 입력 연결 검사; 합성 격자 배정이며 서울 유역 아님',
            'stationByTriangle': [('421' if i % stations == 0 else '401') if owner == 'SURFACE' else None
                                  for i, owner in enumerate(model['rainfallOwner'])],
            'stations': REFERENCES[:stations]}


def observed_coupled():
    model = coupled_case(initial_network=0, exchange_ms=500)
    model['network']['inputText'] = model['network']['inputText'].replace('01/01/2020', '08/08/2022')
    model['network']['inputText'] = model['network']['inputText'].replace('00:00:00', '09:00:00')
    model['network']['inputText'] = model['network']['inputText'].replace('00:02:01', '09:02:01')
    model['network']['timeZone'] = 'UTC'
    model['observedRainfall'] = specification(model['surface'], end='2022-08-08T09:02:00Z')
    return model


class ObservedRainfallTests(unittest.TestCase):
    def test_original_aws_is_rebuilt_and_simplified_schedule_preserves_zero_intervals(self):
        model = mesh(2, 2)
        schedule = compile_rainfall(specification(model), model, 359 * 60)
        self.assertEqual(schedule.summary['stations'][0]['depthMm'], 85)
        self.assertEqual(schedule.summary['expectedSurfaceRainfallM3'], 8.5)
        self.assertLess(schedule.summary['rateChangeCount'], 359)
        self.assertEqual(schedule.events[:3], [
            {'timeMilliseconds': 0, 'ratesMmHByStation': {'421': 30.}},
            {'timeMilliseconds': 60000, 'ratesMmHByStation': {'421': 60.}},
            {'timeMilliseconds': 240000, 'ratesMmHByStation': {'421': 30.}}])
        self.assertEqual(schedule.events[-1]['ratesMmHByStation']['421'], 0.)
        self.assertEqual(len(schedule.source_files), 3)

    def test_utc_window_coverage_and_complete_station_assignment(self):
        model = mesh(2, 2)
        for value in ('2022-08-08T09:00:00', '2022-08-08T09:00:01Z', '2022-08-08T08:59:00Z'):
            spec = specification(model, end='2022-08-08T09:02:00Z')
            spec['startUtc'] = value
            with self.assertRaises(FloodModelError):
                compile_rainfall(spec, model, 120)
        spec = specification(model, end='2022-08-08T15:00:00Z')
        with self.assertRaisesRegex(FloodModelError, 'COVERAGE_INCOMPLETE'):
            compile_rainfall(spec, model, 360 * 60)
        spec = specification(model)
        spec['stationByTriangle'][0] = None
        with self.assertRaisesRegex(FloodModelError, 'OWNERSHIP_INVALID'):
            compile_rainfall(spec, model, 359 * 60)
        spec['stationByTriangle'][0] = '401'
        with self.assertRaisesRegex(FloodModelError, 'ASSIGNMENT_INCOMPLETE'):
            compile_rainfall(spec, model, 359 * 60)

    def test_area_owned_by_network_never_receives_surface_rain(self):
        model = mesh(2, 2)
        model['rainfallOwner'][0] = 'NETWORK'
        spec = specification(model, stations=2)
        result = compile_rainfall(spec, model, 359 * 60)
        self.assertEqual([row['surfaceAreaM2'] for row in result.summary['stations']], [50., 37.5])
        self.assertAlmostEqual(result.summary['expectedSurfaceRainfallM3'], 50*.2885 + 37.5*.085)
        spec['stationByTriangle'][0] = '421'
        with self.assertRaisesRegex(FloodModelError, 'OWNERSHIP_INVALID'):
            compile_rainfall(spec, model, 359 * 60)

    def test_changed_derived_rain_is_rejected_even_when_its_hash_is_recomputed(self):
        data, files = read_station(REFERENCES[0])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name, body in files.items():
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(body)
            data['depthsMm'][0] = 100
            encoded = json.dumps(data).encode()
            (root / 'data/derived/rainfall' / REFERENCES[0]['file']).write_bytes(encoded)
            with self.assertRaisesRegex(FloodModelError, 'DERIVATION_MISMATCH'):
                read_station(REFERENCES[0] | {'sha256': hashlib.sha256(encoded).hexdigest()}, root)
        with self.assertRaisesRegex(FloodModelError, 'REFERENCE_INVALID'):
            read_station(REFERENCES[0] | {'file': '../secret'})

    def test_conflicting_rain_and_inconsistent_network_clock_rejected_before_execution(self):
        with tempfile.TemporaryDirectory() as temporary:
            model = observed_coupled()
            model['surfaceRainfall'] = [{'timeMilliseconds': 0, 'ratesMmH': [], 'evidence': 'TEST'}]
            with self.assertRaisesRegex(FloodModelError, 'FORCING_CONFLICT'):
                run_coupled(model, Path(temporary) / 'conflict')
            model = observed_coupled()
            model['network']['timeZone'] = 'Asia/Seoul'
            with self.assertRaisesRegex(FloodModelError, 'CLOCK_MISMATCH'):
                run_coupled(model, Path(temporary) / 'clock')
            self.assertFalse(any(Path(temporary).iterdir()))


@unittest.skipUnless(find_spec('anuga'), 'flood 선택 의존성 설치 필요')
class ObservedRainfallEngineTests(unittest.TestCase):
    def test_full_observed_window_two_stations_and_replay(self):
        model = mesh(2, 2)
        model['maxStepSeconds'] = .1
        spec = specification(model, stations=2)
        with tempfile.TemporaryDirectory() as temporary:
            first = run_observed_surface(model, spec, Path(temporary) / 'first')
            second = run_observed_surface(model, spec, Path(temporary) / 'second')
            self.assertEqual(first['final'], second['final'])
            self.assertAlmostEqual(first['final']['storageM3'], 50 * (.085 + .2885), places=8)
            self.assertLess(abs(first['observedRainfall']['volumeResidualM3']), 1e-8)
            self.assertEqual(first['numericalStatus'], 'PASSED')
            self.assertFalse(first['rankingEligible'])

    def test_coupled_observed_rain_enters_and_drains_with_matching_ledger(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = run_coupled(observed_coupled(), Path(temporary) / 'coupled')
            self.assertEqual(result['numericalStatus'], 'PASSED')
            self.assertAlmostEqual(result['observedRainfall']['appliedSurfaceRainfallM3'], .006, places=10)
            self.assertGreater(result['balance']['surfaceToNetworkM3'], 0)
            self.assertLess(abs(result['balance']['balanceResidualM3']), 1e-5)

    def test_station_binding_rejects_direct_array_and_missing_station(self):
        model = mesh(2, 2)
        model['rainfallStationIds'] = ['421'] * 8
        with tempfile.TemporaryDirectory() as temporary:
            with EngineProcess('surface', model, Path(temporary) / 'array') as session:
                with self.assertRaisesRegex(FloodModelError, 'BINDING_REQUIRED'):
                    session.call('set_rainfall', [30.] * 8)
            with EngineProcess('surface', model, Path(temporary) / 'station') as session:
                with self.assertRaisesRegex(FloodModelError, 'STATION_RAINFALL_INVALID'):
                    session.call('set_station_rainfall', {'401': 30})

    def test_large_step_instability_is_retained_as_failure(self):
        model = mesh(2, 2)
        model['maxStepSeconds'] = 30
        spec = specification(model, end='2022-08-08T09:02:00Z', stations=2)
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / 'failed'
            with self.assertRaisesRegex(FloodModelError, 'BALANCE_FAILED'):
                run_observed_surface(model, spec, output)
            failure = json.loads((output / 'observed-surface-failure.json').read_bytes())
            self.assertEqual(failure['lastSurface']['timeSeconds'], 60)
            self.assertGreater(failure['maximumForcingBoundaryBalanceResidualM3'], .001)
            self.assertFalse((output / 'observed-surface-result.json').exists())
