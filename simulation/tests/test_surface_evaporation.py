"""원 기상 재산정·시간 구간·지표 가용수량과 결합 손실 원장 검사."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from waterleague_sim.engine.coupled_flood import run_coupled
from waterleague_sim.engine.flood_errors import FloodModelError
from waterleague_sim.engine.flood_process import EngineProcess
from waterleague_sim.engine.swmm import ROOT
from waterleague_sim.forcing.reference_evaporation import read_reference
from waterleague_sim.forcing.surface_evaporation import EvaporationSeries, TRANSFER
from waterleague_sim.forcing.surface_run import run_observed_surface
from waterleague_sim.reference.flood_cases import mesh
from test_surface_infiltration import soils
from test_observed_surface_rainfall import specification, observed_coupled


def reference(event):
    name = event + '-fao56-v1.json'
    return {'file': name, 'sha256': hashlib.sha256((ROOT / 'data/derived/evaporation' / name).read_bytes()).hexdigest()}


def archived():
    return {'schemaVersion': 1, 'type': 'ARCHIVED_FAO56', 'ownershipPolicy': 'SURFACE_ONLY',
            'surfaceTransfer': TRANSFER, 'evidence': '기준 잔디 증발산의 합성 지표 연결 검사',
            'reference': reference('seoul-20220808')}


def numerical(model, rates=(24., 48.), durations=(60, 60)):
    start = datetime(2020, 1, 1, tzinfo=timezone.utc)
    model.update(schemaVersion=2, startUtc=start.isoformat(), durationSeconds=sum(durations))
    intervals, cursor = [], start
    for rate, seconds in zip(rates, durations):
        end = cursor + timedelta(seconds=seconds)
        intervals.append({'startUtc': cursor.isoformat(), 'endUtc': end.isoformat(), 'rateMmDay': rate})
        cursor = end
    return {'schemaVersion': 1, 'type': 'NUMERICAL_TEST_SERIES', 'ownershipPolicy': 'SURFACE_ONLY',
            'surfaceTransfer': TRANSFER, 'evidence': 'NUMERICAL_TEST_ONLY',
            'maximumIntervalSeconds': max(durations), 'intervals': intervals}


class ReferenceEvaporationTests(unittest.TestCase):
    def test_three_archives_rebuild_from_original_weather(self):
        expected = {'seoul-20220808': (359, .031960357088299376),
                    'seoul-20110727': (719, .28355432678358555), 'seoul-20100921': (600, .18978030855022532)}
        for event, (count, depth) in expected.items():
            value, files, hashes = read_reference(reference(event))
            self.assertEqual(len(value['ratesMmDay']), count)
            self.assertAlmostEqual(sum(value['ratesMmDay']) / 1440, depth, places=14)
            self.assertTrue(hashes)
            self.assertTrue(any(name.startswith('reconstruction-calculation/') for name in files))
            if event == 'seoul-20110727':
                self.assertEqual(value['timePolicy'], 'ARCHIVED_DAILY_MEAN_HELD_WITHIN_DAY_NOT_LIVE')

    def test_modified_derived_rates_fail_even_with_changed_file_hash(self):
        ref = reference('seoul-20220808')
        value, files, _ = read_reference(ref)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name, raw in files.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(raw)
            restored, _, _ = read_reference(ref, root)
            self.assertEqual(restored, value)
            value['ratesMmDay'][0] += 1
            encoded = json.dumps(value).encode()
            (root / 'data/derived/evaporation' / ref['file']).write_bytes(encoded)
            with self.assertRaisesRegex(FloodModelError, 'DERIVATION_MISMATCH'):
                read_reference(ref | {'sha256': hashlib.sha256(encoded).hexdigest()}, root)
        with self.assertRaisesRegex(FloodModelError, 'REFERENCE_INVALID'):
            read_reference(ref | {'file': '../secret'})

    def test_exact_interval_integral_no_gaps_overlap_or_extrapolation(self):
        model = mesh(1, 1)
        spec = numerical(model)
        series = EvaporationSeries(spec, model)
        self.assertAlmostEqual(series.step_depth_m(0, 60), 1 / 60000)
        self.assertAlmostEqual(series.step_depth_m(60, 60), 1 / 30000)
        spec['intervals'][0]['rateMmDay'] = 0
        self.assertAlmostEqual(series.step_depth_m(0, 60), 1 / 60000)
        with self.assertRaisesRegex(FloodModelError, 'STRADDLED'):
            series.step_depth_m(59, 2)
        with self.assertRaisesRegex(FloodModelError, 'WINDOW_EXCEEDED'):
            series.step_depth_m(120, 1)
        for time in ('2020-01-01T00:00:59Z', '2020-01-01T00:01:01Z'):
            broken = deepcopy(spec)
            broken['intervals'][1]['startUtc'] = time
            with self.assertRaisesRegex(FloodModelError, 'GAP_OR_OVERLAP'):
                EvaporationSeries(broken, model)

    def test_time_and_source_policy_must_match_before_output_creation(self):
        model = mesh(2, 2)
        model.update(schemaVersion=2, startUtc='2022-08-08T09:01:00Z', durationSeconds=120,
                     evaporation=archived())
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(FloodModelError, 'RAIN_CLOCK_MISMATCH'):
                run_observed_surface(model, specification(model, end='2022-08-08T09:02:00Z'), Path(temporary) / 'run')
            self.assertFalse(any(Path(temporary).iterdir()))
        model = mesh(1, 1)
        spec = numerical(model)
        model['evidence'] = 'REAL_FIELD_OBSERVATIONS'
        with self.assertRaisesRegex(FloodModelError, 'SOURCE_KIND_INVALID'):
            EvaporationSeries(spec, model)


class SurfaceEvaporationTests(unittest.TestCase):
    def test_piecewise_evaporation_and_output_boundaries(self):
        model = mesh(2, 2, water=lambda x, z: x * 0 + .01)
        model['evaporation'] = numerical(model)
        model['maxStepSeconds'] = 30
        results = []
        with tempfile.TemporaryDirectory() as temporary:
            for name, steps in [('full', [120]), ('segmented', [30]*4), ('replay', [120])]:
                with EngineProcess('surface', model, Path(temporary) / name) as engine:
                    for dt in steps:
                        result = engine.call('advance', dt)
                    final = engine.call('finish')
                self.assertAlmostEqual(result['surfaceEvaporationM3'], .005, places=10)
                self.assertAlmostEqual(result['potentialSurfaceEvaporationM3'], .005, places=10)
                self.assertAlmostEqual(result['storageM3'], .995, places=10)
                self.assertTrue(final['evaporation']['complete'])
                self.assertEqual(final['numericalStatus'], 'PASSED')
                results.append(result)
            for key, value in results[0].items():
                if isinstance(value, list):
                    for a, b in zip(value, results[1][key]):
                        self.assertAlmostEqual(a, b, places=12)
                else:
                    self.assertAlmostEqual(value, results[1][key], places=12)
            self.assertEqual(results[0], results[2])

    def test_dry_water_limit_and_network_owned_area_exclusion(self):
        model = mesh(1, 1, water=lambda x, z: x * 0 + .00001)
        model['rainfallOwner'][1] = 'NETWORK'
        model['evaporation'] = numerical(model, (100.,), (60,))
        with tempfile.TemporaryDirectory() as temporary:
            with EngineProcess('surface', model, Path(temporary) / 'run') as engine:
                result = engine.call('advance', 60)
                final = engine.call('finish')
        # 내부 흐름이 두 삼각형을 연결하므로 소유 면적만으로 총 제거량을 고정하지 않는다.
        self.assertAlmostEqual(result['potentialSurfaceEvaporationM3'], 50 * .1 / 1440, places=12)
        self.assertGreater(result['unmetSurfaceEvaporationM3'], 0.)
        self.assertGreaterEqual(min(result['depthM']), 0.)
        self.assertLessEqual(result['surfaceEvaporationM3'], .001 + 1e-10)
        self.assertEqual(final['evaporation']['surfaceAreaM2'], 50.)
        self.assertLess(abs(result['balanceResidualM3']), 1e-9)

    def test_combined_rain_infiltration_and_evaporation_balance(self):
        model = mesh(2, 2, water=lambda x, z: x * 0 + .01)
        model.update(schemaVersion=2, startUtc='2022-08-08T09:00:00Z', durationSeconds=120,
                     evaporation=archived(), infiltration=soils(model))
        with tempfile.TemporaryDirectory() as temporary:
            result = run_observed_surface(model, specification(model, end='2022-08-08T09:02:00Z'), Path(temporary) / 'run')
        final = result['final']
        self.assertGreater(final['surfaceEvaporationM3'], 0.)
        self.assertGreater(final['infiltrationM3'], 0.)
        self.assertAlmostEqual(final['rainfallM3'], .15, places=10)
        self.assertAlmostEqual(1 + final['rainfallM3'] - final['infiltrationM3']
                               - final['surfaceEvaporationM3'], final['storageM3'], places=9)
        self.assertEqual(result['numericalStatus'], 'PASSED')

    def test_observed_coupled_loss_ledger(self):
        model = observed_coupled()
        model['surface'].update(schemaVersion=2, startUtc='2022-08-08T09:00:00Z', durationSeconds=120,
                               evaporation=archived(), infiltration=soils(model['surface'], deficit=.3))
        model['surface']['initialDepthM'] = [.01] * len(model['surface']['triangles'])
        with tempfile.TemporaryDirectory() as temporary:
            result = run_coupled(model, Path(temporary) / 'run')
        balance = result['balance']
        self.assertGreater(balance['surfaceEvaporationM3'], 0.)
        self.assertAlmostEqual(balance['surfaceRainfallM3'] - balance['surfaceInfiltrationM3']
            - balance['surfaceEvaporationM3'] + balance['surfaceBoundaryNetInflowM3'],
            balance['surfaceExternalNetInflowM3'], places=9)
        self.assertLess(abs(balance['exchangeCancellationResidualM3']), 1e-8)
        self.assertTrue(result['surfaceEvaporation']['complete'])
        self.assertEqual(result['numericalStatus'], 'PASSED')


if __name__ == '__main__':
    unittest.main()
