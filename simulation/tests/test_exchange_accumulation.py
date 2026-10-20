"""장시간 부호 교환 원장의 덧셈 오차와 작은 증분 보존."""
import math
import unittest
from waterleague_sim.engine.accumulation import CompensatedSum


class ExchangeAccumulationTests(unittest.TestCase):
    def test_large_signed_cancellation_preserves_small_transfers(self):
        for values in ([1e16, 1., -1e16], [-1e16, -.1, 1e16],
                       [1e6, *([.01, -.02, .03] * 100000), -1e6]):
            total = CompensatedSum()
            for value in values:
                total.add(value)
            self.assertEqual(total.value, math.fsum(values))

    def test_long_positive_then_negative_ledger_matches_independent_fsum(self):
        values = [((i % 29) + 1)/7 for i in range(100000)]
        values += [-v/3 for v in reversed(values)]
        total = CompensatedSum()
        for value in values:
            total.add(value)
        self.assertEqual(total.value, math.fsum(values))


if __name__ == '__main__':
    unittest.main()
