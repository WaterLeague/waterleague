"""플랫폼 수학 라이브러리의 반올림과 파생 입력 변조의 구분."""
import math
import unittest

from waterleague_sim.forcing.reconstruction import equivalent


class ReconstructionTests(unittest.TestCase):
    def test_archived_macos_and_linux_radiation_roundoff(self):
        macos = {'hours': [{'clearSkyMjM2': 0.07694908722459469,
                           'extraterrestrialMjM2': 0.10236492687850808}]}
        linux = {'hours': [{'clearSkyMjM2': 0.07694908722459395,
                           'extraterrestrialMjM2': 0.1023649268785071}]}
        self.assertTrue(equivalent(macos, linux))

    def test_changed_values_structure_and_nonfinite_values_are_rejected(self):
        for left, right in [(0.08, 0.080000000001), (1, 2), (True, 1),
                            ([0.08], []), ({'rate': 0.08}, {'depth': 0.08}),
                            ('2022-08-08', '2022-08-09'),
                            (math.inf, math.inf), (math.nan, math.nan)]:
            with self.subTest(left=left, right=right):
                self.assertFalse(equivalent(left, right))
