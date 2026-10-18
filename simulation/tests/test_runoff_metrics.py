"""원 단계 합산·선행 구간 제외·첨두 시각 및 잔여 저류 보존."""
from datetime import datetime, timezone
import unittest
from waterleague_sim.engine.runoff_metrics import RunoffMetrics
from waterleague_sim.engine.swmm import SimulationQualityError


class RunoffMetricsTests(unittest.TestCase):
    def test_same_step_combined_peak_excludes_warmup_and_is_not_sum_of_peaks(self):
        clock = datetime(2022, 8, 8, tzinfo=timezone.utc)
        m = RunoffMetrics(10, 40, clock, 10)
        for args in ((10, 100, 100), (20, 5, 0), (30, 0, 4), (40, 2, 2)):
            m.observe(*args)
        result = m.finish()
        self.assertEqual(result['peakM3s'], 5)
        self.assertEqual(result['peakAt'], '2022-08-08T00:00:20+00:00')
        self.assertEqual(result['dischargeIntegralM3'], 130)
        self.assertEqual(result['observedSeconds'], 30)
        self.assertEqual(result['stepCount'], 3)

    def test_missing_native_step_partial_window_and_negative_physical_flow_rejected(self):
        clock = datetime(2022, 8, 8, tzinfo=timezone.utc)
        for args in ((20, 1, 0), (10, -1e-4, 0), (10, float('nan'), 0)):
            with self.subTest(args=args), self.assertRaises(SimulationQualityError):
                RunoffMetrics(0, 30, clock, 10).observe(*args)
        m = RunoffMetrics(0, 30, clock, 10)
        m.observe(10, 0, 0)
        with self.assertRaises(SimulationQualityError):
            m.finish()
        m.observe(20, -1e-18, 0)
        m.observe(30, 0, 0)
        self.assertEqual(m.finish()['minimumComponentRateM3s'], -1e-18)
        self.assertIsNone(m.finish()['peakAt'])


if __name__ == '__main__':
    unittest.main()
