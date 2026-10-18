"""서로 다른 시각의 출구 첨두와 프레임 독립성·기존 계산 보존 검사."""
from pathlib import Path
import tempfile
import unittest
from waterleague_sim.engine.facility_metrics import library_path
from waterleague_sim.engine.flood_process import EngineProcess
from waterleague_sim.engine.swmm import ROOT

MODEL = '''[TITLE]
Synthetic staggered outfalls, not Seoul
[OPTIONS]
FLOW_UNITS CMS
FLOW_ROUTING DYNWAVE
START_DATE 01/01/2022
START_TIME 00:00:00
REPORT_START_DATE 01/01/2022
REPORT_START_TIME 00:00:00
END_DATE 01/01/2022
END_TIME 00:02:00
REPORT_STEP 00:00:01
ROUTING_STEP 0.1
MINIMUM_STEP 0.1
VARIABLE_STEP 0
ALLOW_PONDING NO
[JUNCTIONS]
A 0 3 0 0 0
B 0 3 0 0 0
[OUTFALLS]
O1 -1 FREE NO
O2 -1 FREE NO
[CONDUITS]
C1 A O1 5 .014 0 0
C2 B O2 5 .014 0 0
[XSECTIONS]
C1 CIRCULAR 1 0 0 0 1
C2 CIRCULAR 1 0 0 0 1
[INFLOWS]
A FLOW EARLY FLOW 1 1 0
B FLOW LATE FLOW 1 1 0
[TIMESERIES]
EARLY 0:00:00 0
EARLY 0:00:10 .1
EARLY 0:00:20 .1
EARLY 0:00:30 0
EARLY 0:02:00 0
LATE 0:00:00 0
LATE 0:00:50 0
LATE 0:01:00 .1
LATE 0:01:10 .1
LATE 0:01:20 0
LATE 0:02:00 0
[REPORT]
NODES ALL
LINKS ALL
'''


@unittest.skipUnless(library_path().exists(), '출구 관측 네이티브 빌드 필요')
class FacilityMetricsTests(unittest.TestCase):
    def test_simultaneous_peak_not_sum_of_peaks_and_frame_interval_does_not_change_physics(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'tmp', prefix='peaks-') as temporary:
            root = Path(temporary)
            results = []
            for name, engine, interval in (('old', 'facility_network', 60),
                                            ('fine', 'facility_metrics', 1),
                                            ('coarse', 'facility_metrics', 60)):
                with EngineProcess(engine, MODEL, root/name, native_duration=True) as process:
                    results.append(process.call('run', interval)['result'])
            self.assertEqual(results[1]['evaluationMetrics'], results[2]['evaluationMetrics'])
            for name in ('fine', 'coarse'):
                self.assertEqual((root/'old/network.out').read_bytes(), (root/name/'network.out').read_bytes())
            metrics = results[1]['evaluationMetrics']
            self.assertTrue(metrics['complete'])
            self.assertGreater(metrics['combined']['peakOutwardM3s'], .09)
            self.assertLess(metrics['combined']['peakOutwardM3s'],
                            .75 * sum(v['peakOutwardM3s'] for v in metrics['outfalls'].values()))
            self.assertLess(metrics['outfalls']['O1']['peakOutwardTimeSeconds'], 40)
            self.assertGreater(metrics['outfalls']['O2']['peakOutwardTimeSeconds'], 50)
            self.assertEqual(metrics['combined']['inwardVolumeM3'], 0)
            self.assertAlmostEqual(metrics['combined']['outwardVolumeM3'], 4, delta=.03)


if __name__ == '__main__': unittest.main()
