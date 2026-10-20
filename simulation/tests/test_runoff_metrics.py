"""원 단계 합산·선행 구간 제외·첨두 시각 및 잔여 저류 보존."""
from datetime import datetime, timezone
import unittest
from waterleague_sim.engine.runoff_metrics import RunoffMetrics, comparison
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
        self.assertEqual(result['timing']['status'], 'COMPUTED')
        self.assertEqual(result['timing']['firstMomentM3Seconds'], 1850)
        self.assertAlmostEqual(result['timing']['centroidSeconds'], 1850 / 130)

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
        self.assertEqual(m.finish()['timing']['status'], 'WITHHELD')
        self.assertEqual(m.finish()['timing']['reason'], 'NEGATIVE_COMPONENT_RATE')
        self.assertIsNone(m.finish()['timing']['centroidSeconds'])

    def test_translated_pulses_have_signed_delay_and_no_volume_score(self):
        early = analytical_run([2, 0, 0, 0])
        late = analytical_run([0, 0, 2, 0])
        for base, design, delay in ((early, late, 20), (late, early, -20), (early, early, 0)):
            with self.subTest(delay=delay):
                result = comparison(base, design)
                self.assertEqual(result['detention']['centroidDelaySeconds'], delay)
                self.assertEqual(result['detention']['status'], 'COMPARABLE')
                self.assertFalse(result['detention']['rankingEligible'])
                self.assertEqual(result['accountedReductionM3'], 0)

    def test_no_discharge_is_undefined_and_negative_rate_takes_priority(self):
        dry, wet = analytical_run([0, 0]), analytical_run([1, 0])
        negative = analytical_run([1, -1e-18])
        for base, design, status, reason in (
            (dry, wet, 'UNAVAILABLE', 'BASELINE_NO_DISCHARGE'),
            (wet, dry, 'UNAVAILABLE', 'STRATEGY_NO_DISCHARGE'),
            (dry, dry, 'UNAVAILABLE', 'BASELINE_NO_DISCHARGE'),
            (negative, wet, 'WITHHELD', 'BASELINE_NEGATIVE_COMPONENT_RATE'),
            (dry, negative, 'WITHHELD', 'STRATEGY_NEGATIVE_COMPONENT_RATE'),
        ):
            with self.subTest(reason=reason):
                result = comparison(base, design)['detention']
                self.assertEqual((result['status'], result['reason']), (status, reason))
                self.assertIsNone(result['centroidDelaySeconds'])
        self.assertGreater(negative['runoffMetrics']['timing']['firstMomentM3Seconds'], 0)

    def test_constant_interval_partition_preserves_first_moment(self):
        coarse = analytical_run([1, 3, 2], step=10)['runoffMetrics']
        fine = analytical_run([1] * 10 + [3] * 10 + [2] * 10, step=1)['runoffMetrics']
        self.assertEqual(coarse['timing'], fine['timing'])
        self.assertEqual(coarse['timing']['firstMomentM3Seconds'], 1000)
        self.assertAlmostEqual(coarse['timing']['centroidSeconds'], 1000 / 60)

    def test_overflow_and_unaligned_activation_are_rejected(self):
        clock = datetime(2022, 8, 8, tzinfo=timezone.utc)
        with self.assertRaises(SimulationQualityError):
            RunoffMetrics(0, 30, clock, 10).observe(10, 1e308, 0)
        with self.assertRaises(SimulationQualityError):
            RunoffMetrics(5, 30, clock, 10).observe(10, 1, 0)


def analytical_run(flows, step=10):
    """직사각형 파형의 적분 해로 비교 규약 검증."""
    clock = datetime(2022, 8, 8, tzinfo=timezone.utc)
    m = RunoffMetrics(0, len(flows) * step, clock, step)
    for index, flow in enumerate(flows):
        m.observe((index + 1) * step, flow, 0)
    metrics = m.finish()
    volume = metrics['dischargeIntegralM3']
    return {'initial': {'at': metrics['start']}, 'runoffMetrics': metrics,
        'final': {'at': metrics['end'], 'surfaceRunoffM3': volume, 'lidDrainageM3': 0,
            'initialStorageM3': 0, 'storageM3': 0, 'accountedDischargeM3': volume,
            'precipitationM3': volume, 'infiltrationM3': 0, 'evaporationM3': 0,
            'balanceResidualM3': 0}}


if __name__ == '__main__':
    unittest.main()
