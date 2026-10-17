"""자정 누적 초기화·관측 결측을 실제 강우로 혼동하지 않는 검사."""
import copy
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from waterleague_sim.ingestion.live import KST, normalized, parse
from waterleague_sim.ingestion.rainfall import RainfallQualityError


class LiveForcingTests(unittest.TestCase):
    def fixture(self):
        start = datetime(2026, 10, 17, 23, 0, tzinfo=KST)
        rows, depths = {}, []
        day = Decimal(0)
        for i in range(181):
            at = start+timedelta(minutes=i)
            depth = Decimal('.5') if 55 <= i < 75 else Decimal(0)
            depths.append(depth)
            if at.hour == 0 and at.minute == 0:
                day = Decimal(0)
            day += depth
            rows[at.astimezone(timezone.utc)] = {
                'dayMm': day, 'fifteenMinuteMm': sum(depths[max(0, i-14):i+1]),
                'sixtyMinuteMm': sum(depths[max(0, i-59):i+1]),
                'temperatureC': Decimal(20), 'humidityPercent': Decimal(60),
                'windSpeedMs': Decimal(2), 'pressureHpa': None}
        return rows, start.astimezone(timezone.utc)

    def test_continuous_rain_crosses_midnight_from_observed_moving_totals(self):
        rows, start = self.fixture()
        result = normalized(rows, start+timedelta(minutes=50), start+timedelta(minutes=180))
        self.assertEqual(sum(v['depthMm'] for v in result), 10)
        for i in (9, 10):
            self.assertEqual(result[i]['depthMm'], .5)
            self.assertEqual(result[i]['method'], 'ROLLING_15_MINUTE_DIFFERENCE')
        self.assertIsNone(result[-1]['weather']['pressureHpa'])
        self.assertEqual(result[-1]['weather']['temperatureC'], 20)

    def test_missing_row_and_conflicting_totals_never_become_zero(self):
        rows, start = self.fixture()
        missing = copy.deepcopy(rows)
        del missing[start+timedelta(minutes=63)]
        with self.assertRaises(RainfallQualityError):
            normalized(missing, start+timedelta(minutes=50), start+timedelta(minutes=180))
        mismatch = copy.deepcopy(rows)
        mismatch[start+timedelta(minutes=65)]['sixtyMinuteMm'] += 1
        with self.assertRaises(RainfallQualityError):
            normalized(mismatch, start+timedelta(minutes=50), start+timedelta(minutes=180))

    def test_wrong_station_and_nan_are_rejected(self):
        at = datetime(2026, 10, 17, tzinfo=KST)
        row = '202610170000 421 0 0 0 0 0 0 20 0 0 0 0 0 60 1000 1010 10'
        def source(value):
            return ('#START7777\n# RN-15m RN-60m RN-12H RN-DAY\n'+value+'\n#7777END').encode()
        self.assertEqual(len(parse(source(row), '421', at, at)), 1)
        for value in (row.replace('421', '108'), row.replace(' 20 ', ' NaN '), row+'\n'+row):
            with self.assertRaises(RainfallQualityError):
                parse(source(value), '421', at, at)


if __name__ == '__main__':
    unittest.main()
