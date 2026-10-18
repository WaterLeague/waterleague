"""관망 시계열 경계의 원본 보존·단위·역류·결합 검증."""
from copy import deepcopy
from datetime import datetime, timedelta
from importlib.util import find_spec
import json
from pathlib import Path
import tempfile
import unittest

from waterleague_sim.engine.flood_errors import FloodModelError
from waterleague_sim.engine.flood_process import EngineProcess
from waterleague_sim.engine.network import NetworkSession, library_path
from waterleague_sim.engine.network_exchange import ExchangeNetworkSession
from waterleague_sim.engine.coupled_flood import run_coupled
from waterleague_sim.forcing.network_stage import prepare_network_stage
from waterleague_sim.reference.flood_cases import tank_input, coupled_limited_case

START = '2020-01-01T00:00:00+00:00'


def boundary(values):
    start = datetime.fromisoformat(START)
    return {'type': 'TIME_SERIES_STAGE', 'unit': 'm', 'interpolation': 'LINEAR',
        'maximumGapSeconds': 120, 'momentum': 'SWMM_DYNAMIC_WAVE',
        'verticalDatum': 'ANALYTICAL_ZERO', 'referenceStatus': 'LOCAL_DIAGNOSTIC',
        'evidence': 'NUMERICAL_TEST_ONLY_NOT_OBSERVED',
        'samples': [{'timeUtc': (start + timedelta(seconds=t)).isoformat(), 'stageM': h}
                    for t, h in values]}


def model(units='CMS'):
    return {'inputText': tank_input().replace('FLOW_UNITS CMS', 'FLOW_UNITS ' + units),
        'verticalDatum': 'ANALYTICAL_ZERO', 'coordinateSystem': 'LOCAL_REFERENCE_METRES',
        'timeZone': 'UTC', 'startUtc': START, 'durationSeconds': 120,
        'outfallStageBoundaries': {'OUT': boundary([(0, 1), (30, 2), (60, 2), (90, 0), (120, 0)])}}


class NetworkStageContractTests(unittest.TestCase):
    def test_session_snapshot_does_not_follow_later_caller_edits(self):
        source = coupled_limited_case()
        with tempfile.TemporaryDirectory() as root:
            session = ExchangeNetworkSession(source['network'] | {'ports': source['ports']},
                                              Path(root) / 'unused', evaluation_seconds=5)
            source['ports'][0]['outfall'] = 'OUT'
            self.assertEqual(session.model['ports'][0]['outfall'], 'SURFACE')
            self.assertFalse((Path(root) / 'unused').exists())

    def test_compilation_preserves_nonboundary_lines_and_flap(self):
        source = model()
        source['inputText'] = source['inputText'].replace('OUT 0 FIXED 0 NO', 'OUT 0 FREE YES ; 원본 경계')
        before = deepcopy(source)
        output = prepare_network_stage(source, evaluation_seconds=120)
        self.assertEqual(source, before)
        original = source['inputText'].splitlines()
        prepared = output.text.splitlines()
        for a, b in zip(original, prepared):
            if a.startswith('OUT '):
                self.assertIn('TIMESERIES WL_STAGE_', b)
                self.assertTrue(b.endswith('YES ; 원본 경계'))
            else:
                self.assertEqual(a, b)
        self.assertEqual(output.summary['outfalls']['OUT']['headInterpretation'],
                         'WATER_SURFACE_ELEVATION_NOT_DEPTH')
        self.assertEqual(output.summary['outfalls']['OUT']['momentum'], 'SWMM_DYNAMIC_WAVE')

    def test_us_length_conversion_and_fractional_clock(self):
        source = model('CFS')
        source['outfallStageBoundaries']['OUT'] = boundary([(0, .3048), (1.25, .6096), (120, .3048)])
        output = prepare_network_stage(source)
        lines = [line.split() for line in output.text.splitlines() if line.startswith('WL_STAGE_')]
        self.assertEqual([float(row[3]) for row in lines], [1, 2, 1])
        self.assertAlmostEqual(float(lines[1][2]) * 3600, 1.25, places=12)

    def test_incomplete_clock_duplicate_binding_and_overwrite_are_rejected(self):
        variants = []
        value = model(); value['outfallStageBoundaries']['OUT']['samples'].pop(); variants.append((value, 'COVERAGE'))
        value = model(); value['timeZone'] = 'Asia/Seoul'; variants.append((value, 'CLOCK'))
        value = model(); value['ports'] = [{'outfall': 'out'}]; variants.append((value, 'EXCHANGE_CONFLICT'))
        value = model(); value['outfallStageBoundaries']['TANK'] = value['outfallStageBoundaries'].pop('OUT'); variants.append((value, 'OUTFALL_REQUIRED'))
        value = model(); value['outfallStageBoundaries']['out'] = value['outfallStageBoundaries']['OUT']; variants.append((value, 'DUPLICATE_OUTFALL'))
        value = model(); value['inputText'] = value['inputText'].replace('OUT 0 FIXED 0', 'OUT 0 TIMESERIES OLD'); variants.append((value, 'EXISTING_SERIES_CONFLICT'))
        for value, code in variants:
            with self.subTest(code=code), self.assertRaisesRegex(FloodModelError, code):
                prepare_network_stage(value, evaluation_seconds=120)
        with self.assertRaisesRegex(FloodModelError, 'WINDOW_MISMATCH'):
            prepare_network_stage(model(), evaluation_seconds=121)


@unittest.skipUnless(library_path().exists(), '관망 엔진 빌드 필요')
class NetworkStageEngineTests(unittest.TestCase):
    def test_native_internal_interpolation_reverse_then_drain_and_hashes(self):
        with tempfile.TemporaryDirectory() as root:
            directory = Path(root) / 'native'
            with NetworkSession(model(), directory) as session:
                for seconds, expected in ((15, 1.5), (15, 2), (30, 2)):
                    state = session.advance(seconds)
                    self.assertAlmostEqual(state['nodes']['OUT']['headM'], expected, delta=1e-6)
                self.assertLess(state['links']['PIPE']['flowM3s'], 0)
                self.assertGreater(state['nodes']['OUT']['boundaryInflowM3'], 0)
                self.assertGreater(state['nodes']['TANK']['storageM3'], 10)
                with self.assertRaisesRegex(FloodModelError, 'OVERRIDE_REJECTED'):
                    session.set_outfall_head('OUT', 0)
                final = session.advance(60)
                self.assertGreater(final['links']['PIPE']['flowM3s'], 0)
                self.assertGreater(final['nodes']['OUT']['boundaryOutflowM3'], 0)
                with self.assertRaisesRegex(FloodModelError, 'ALREADY_AT_END'):
                    session.advance(1)
                result = session.finish()
                self.assertEqual(result['numericalStatus'], 'PASSED')
            self.assertEqual((directory / 'network-original.inp').read_text(), model()['inputText'])
            self.assertEqual(result['stageBoundaries'], json.loads((directory / 'network-stage-boundaries.json').read_text()))
            self.assertIn('networkStageAdapterSha256', result['engine'])

    def test_native_cfs_stage_is_metres_at_api_boundary(self):
        source = model('CFS')
        source['outfallStageBoundaries']['OUT'] = boundary([(0, .3048), (60, .6096), (120, .6096)])
        with tempfile.TemporaryDirectory() as root:
            with NetworkSession(source, Path(root) / 'us') as session:
                state = session.advance(60)
                self.assertAlmostEqual(state['nodes']['OUT']['headM'], .6096, delta=1e-6)
                session.advance(60)
                session.finish()

    def test_stride_does_not_turn_linear_stage_into_step_function(self):
        finals = []
        with tempfile.TemporaryDirectory() as root:
            for stride in (1, 30):
                with EngineProcess('network', model(), Path(root) / str(stride)) as session:
                    for _ in range(120 // stride):
                        final = session.call('advance', stride)
                    self.assertEqual(session.call('finish')['numericalStatus'], 'PASSED')
                    finals.append(final)
        self.assertAlmostEqual(finals[0]['nodes']['TANK']['storageM3'],
                               finals[1]['nodes']['TANK']['storageM3'], delta=1e-5)

    @unittest.skipUnless(find_spec('anuga'), '지표 엔진 설치 필요')
    def test_coupled_external_boundary_and_exchange_are_distinct(self):
        outputs = []
        with tempfile.TemporaryDirectory() as root:
            for frame in (50, 1000):
                source = coupled_limited_case()
                source['network'].update(timeZone='UTC', startUtc=START, durationSeconds=5,
                    outfallStageBoundaries={'OUT': boundary([(0, 0), (2.5, .1), (5, 0)])})
                source['surface']['schemaVersion'] = 2
                source['frameIntervalMilliseconds'] = frame
                result = run_coupled(source, Path(root) / str(frame))
                self.assertEqual(result['numericalStatus'], 'PASSED')
                outputs.append(result['balance'])
            self.assertEqual(outputs[0], outputs[1])
            source['network']['outfallStageBoundaries']['SURFACE'] = source['network']['outfallStageBoundaries']['OUT']
            with self.assertRaisesRegex(FloodModelError, 'EXCHANGE_CONFLICT'):
                run_coupled(source, Path(root) / 'conflict')
            self.assertFalse((Path(root) / 'conflict').exists())


if __name__ == '__main__':
    unittest.main()
