"""월류 시간의 내부 단계 결속·지표 저류 제외·물리 출력 보존 검사."""
import ctypes as C
from pathlib import Path
import tempfile
import unittest

from waterleague_sim.engine.facility_metrics import FacilityMetricsSession, library_path
from waterleague_sim.engine.node_flood_duration import METHOD
from waterleague_sim.engine.swmm import ROOT
from test_facility_metrics import MODEL


@unittest.skipUnless(library_path().exists(), '월류 시간 관측 엔진 필요')
class NodeFloodDurationTests(unittest.TestCase):
    def test_native_duration_matches_each_step_and_resets_between_runs(self):
        text = MODEL.replace('A 0 3 0 0 0', 'A 0 .1 0 0 0').replace(
            'C1 CIRCULAR 1 ', 'C1 CIRCULAR .01 ')
        with tempfile.TemporaryDirectory(dir=ROOT/'tmp', prefix='flood-seconds-') as tmp:
            results = {}
            for name, model in (('flood', text), ('dry', text.replace(' .1\n', ' 0\n'))):
                with FacilityMetricsSession(model, Path(tmp)/name, native_duration=True) as s:
                    self.assertEqual(s.initial['nodeFloodingDurationMethod'], METHOD)
                    self.assertTrue(all(n['floodingSeconds'] == 0 for n in s.initial['nodes'].values()))
                    expected, previous = 0., 0.
                    while previous < s.duration_seconds:
                        now = s.advance()
                        if now['nodes']['A']['overflowM3s'] > 0:
                            expected += now['totals']['timeSeconds']-previous
                        previous = now['totals']['timeSeconds']
                    result = s.finish()
                    self.assertEqual(result['final']['nodes']['A']['floodingSeconds'], expected)
                    self.assertEqual(result['final']['nodes']['O1']['floodingSeconds'], 0)
                    results[name] = result
            self.assertGreater(results['flood']['final']['nodes']['A']['floodingSeconds'], 0)
            self.assertLess(results['flood']['final']['nodes']['A']['floodingSeconds'], 36)
            self.assertEqual(results['dry']['final']['nodes']['A']['floodingSeconds'], 0)
            with FacilityMetricsSession(text, Path(tmp)/'coarse', native_duration=True) as s:
                coarse = s.run(60)['result']
            self.assertEqual(coarse['final']['nodes'], results['flood']['final']['nodes'])
            self.assertEqual((Path(tmp)/'coarse/network.out').read_bytes(),
                             (Path(tmp)/'flood/network.out').read_bytes())

    def test_ponding_is_not_external_flooding_and_bad_read_is_rejected(self):
        text = MODEL.replace('ALLOW_PONDING NO', 'ALLOW_PONDING YES').replace(
            'A 0 3 0 0 0', 'A 0 .1 0 0 100').replace('C1 CIRCULAR 1 ', 'C1 CIRCULAR .01 ')
        with tempfile.TemporaryDirectory(dir=ROOT/'tmp', prefix='pond-seconds-') as tmp:
            with FacilityMetricsSession(text, Path(tmp)/'pond', native_duration=True) as s:
                self.assertNotEqual(s.lib.wl_floodDurationRead(-1, (C.c_double*3)(), 3), 0)
                saw_ponding = False
                while s.snapshot()['totals']['timeSeconds'] < s.duration_seconds:
                    value = s.advance()
                    saw_ponding |= value['nodes']['A']['depthM'] > .11
                    self.assertEqual(value['nodes']['A']['floodingSeconds'], 0)
                result = s.finish()
            self.assertTrue(saw_ponding)
            self.assertEqual(result['final']['nodes']['A']['floodingM3'], 0)
            self.assertEqual(result['evaluationMetrics']['floodingDuration']['floodingSeconds'], 0)

    def test_simultaneous_union_partitioned_windows_and_output_interval_independence(self):
        text = MODEL.replace('A 0 3 0 0 0', 'A 0 .1 0 0 0').replace(
            'B 0 3 0 0 0', 'B 0 .1 0 0 0').replace('CIRCULAR 1 ', 'CIRCULAR .01 ')
        text = text.replace('0:00:50', '0:00:10').replace('0:01:00', '0:00:20').replace(
            '0:01:10', '0:00:30').replace('0:01:20', '0:00:40')
        with tempfile.TemporaryDirectory(dir=ROOT/'tmp', prefix='flood-union-') as tmp:
            root = Path(tmp)
            with FacilityMetricsSession(text, root/'whole', native_duration=True) as s:
                previous, expected = 0., 0.
                slices = {'prior': 0., 'event': 0., 'recovery': 0.}
                windows = {'prior': (0, 17.037), 'event': (17.037, 32.063), 'recovery': (32.063, s.duration_seconds)}
                while previous < s.duration_seconds:
                    now = s.advance()
                    end = now['totals']['timeSeconds']
                    active = any(now['nodes'][n]['overflowM3s'] > 0 for n in ('A', 'B'))
                    if active:
                        expected += end-previous
                        for name, (left, right) in windows.items():
                            slices[name] += max(0, min(end, right)-max(previous, left))
                    previous = end
                whole = s.finish()
            measured = whole['evaluationMetrics']['floodingDuration']
            self.assertEqual(measured['floodingSeconds'], expected)
            per_node = [whole['final']['nodes'][n]['floodingSeconds'] for n in ('A', 'B')]
            self.assertGreater(expected, max(per_node))
            self.assertLess(expected, sum(per_node))
            for name, (start, end) in windows.items():
                model = {'inputText': text, 'evaluationWindow': {'schemaVersion': 1,
                    'startMilliseconds': round(start*1000), 'endMilliseconds': round(end*1000)}}
                with FacilityMetricsSession(model, root/name, evaluation_seconds=round(whole['final']['totals']['timeSeconds'])) as s:
                    result = s.run(60)['result']
                duration = result['evaluationMetrics']['floodingDuration']
                self.assertTrue(duration['complete'])
                self.assertEqual(duration['floodingSeconds'], slices[name])
                self.assertEqual(result['final']['nodes'], whole['final']['nodes'])
                self.assertEqual((root/name/'network.out').read_bytes(), (root/'whole/network.out').read_bytes())
            self.assertAlmostEqual(sum(slices.values()), expected, places=9)

    def test_incomplete_and_invalid_windows_are_not_complete_dry_results(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'tmp', prefix='flood-window-') as tmp:
            model = {'inputText': MODEL, 'evaluationWindow': {
                'schemaVersion': 1, 'startMilliseconds': 17037, 'endMilliseconds': 32063}}
            with FacilityMetricsSession(model, Path(tmp)/'incomplete', evaluation_seconds=119) as s:
                s.lib.wl_floodDurationWindow.argtypes = [C.c_double, C.c_double]
                for start, end in ((-1., 2.), (2., 2.), (0., float('nan')), (0., 1000.)):
                    self.assertNotEqual(s.lib.wl_floodDurationWindow(start, end), 0)
                s.advance(18)
                self.assertNotEqual(s.lib.wl_floodDurationWindow(0., 30.), 0)
                result = s.finish()
            self.assertFalse(result['evaluationMetrics']['floodingDuration']['complete'])
            self.assertAlmostEqual(result['evaluationMetrics']['floodingDuration']['coveredSeconds'], .963, places=7)
            self.assertEqual(result['numericalStatus'], 'FAILED')
