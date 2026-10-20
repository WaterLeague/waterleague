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
