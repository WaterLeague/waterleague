import unittest
from datetime import datetime, timedelta
from decimal import Decimal

from waterleague_sim.ingestion.rainfall import RainInterval, RainfallQualityError
from waterleague_sim.ingestion.seoul import KST, aggregate_complete_minutes, annual_audit, normalize_window, parse


class SeoulRainfallTests(unittest.TestCase):
    def setUp(self):
        self.start = datetime(2024, 7, 18, 23, 40, tzinfo=KST)
        self.end = self.start + timedelta(minutes=20)
        self.header = '강우량계명,시간,10분우량\n'

    def normalize(self, body):
        return normalize_window(parse(self.header + body, '뚝섬P'), '902', 'source', self.start, self.end)

    def test_end_minute_and_midnight_are_preserved(self):
        rows, total = self.normalize('뚝섬P,2024-07-18 23:49,0.5\n뚝섬P,2024-07-18 23:59,1\n')
        self.assertEqual(Decimal('1.5'), total)
        self.assertEqual(self.start, rows[0].start)
        self.assertEqual(self.end, rows[-1].end)
        self.assertEqual(timedelta(minutes=10), rows[0].end - rows[0].start)

    def test_bad_windows_fail_without_imputation(self):
        valid = '뚝섬P,2024-07-18 23:49,0.5\n뚝섬P,2024-07-18 23:59,1\n'
        cases = [valid.splitlines()[0], valid + valid.splitlines()[1],
                 valid.replace('23:49', '23:48'), valid.replace('뚝섬P', '성동구청'),
                 valid.replace(',0.5', ',-1'), valid.replace(',0.5', ',NaN'),
                 valid.replace(',0.5', ',Infinity'), valid.replace(',0.5', ','),
                 '\n'.join(reversed(valid.splitlines()))]
        for body in cases:
            with self.subTest(body=body), self.assertRaises(RainfallQualityError):
                self.normalize(body)

    def test_annual_gaps_and_irregular_timestamps_remain_visible(self):
        records = parse(self.header + '뚝섬P,2024-07-18 23:49,0.5\n뚝섬P,2024-07-18 23:49,0.5\n뚝섬P,2024-07-18 23:58,-1\n', '뚝섬P')
        audit = annual_audit(records, 2024)
        self.assertEqual(366 * 144 - 1, audit['missingAlignedIntervals'])
        self.assertEqual(1, audit['duplicateTimestampRows'])
        self.assertEqual(1, audit['irregularTimestampRows'])
        self.assertEqual(1, audit['invalidDepthRows'])

    def test_minute_aggregation_excludes_partial_edges(self):
        start = datetime(2024, 7, 18, 0, 1, tzinfo=KST)
        rows = [RainInterval('421', start + timedelta(minutes=i), start + timedelta(minutes=i + 1),
                            Decimal('0.1'), 'BASIC_CHECKED', str(i)) for i in range(38)]
        grouped, evidence = aggregate_complete_minutes(rows)
        self.assertEqual(2, len(grouped))
        self.assertEqual([Decimal('1.0')] * 2, [row.depth_mm for row in grouped])
        self.assertEqual(9, evidence['excludedLeadingMinutes'])
        self.assertEqual(9, evidence['excludedTrailingMinutes'])
        self.assertEqual(1.8, evidence['excludedDepthMm'])
        self.assertEqual(10, grouped[0].start.minute)
        self.assertEqual(30, grouped[-1].end.minute)
        with self.assertRaises(RainfallQualityError):
            aggregate_complete_minutes(rows[:15] + rows[16:])
        with self.assertRaises(RainfallQualityError):
            aggregate_complete_minutes(rows[:5])


if __name__ == '__main__':
    unittest.main()
