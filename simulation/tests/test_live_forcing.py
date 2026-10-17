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

    def test_antecedent_zero_gap_requires_equal_observed_counter_and_keeps_warnings(self):
        rows, start = self.fixture()
        end = start+timedelta(minutes=180)
        dry_gap = start+timedelta(minutes=120)
        del rows[dry_gap]
        with self.assertRaises(RainfallQualityError):
            normalized(rows, start+timedelta(minutes=50), end)
        values = normalized(rows, start+timedelta(minutes=50), end, rolling_warnings=[])
        filled = next(v for v in values if v['end'] == dry_gap.isoformat())
        self.assertEqual(filled['depthMm'],0)
        self.assertEqual(filled['method'],'OBSERVED_ZERO_COUNTER_GAP')
        del rows[start+timedelta(minutes=63)]
        with self.assertRaises(RainfallQualityError):
            normalized(rows, start+timedelta(minutes=50), end, rolling_warnings=[])
        rows, start = self.fixture()
        rows[start+timedelta(minutes=65)]['sixtyMinuteMm'] += 1
        warnings = []
        normalized(rows,start+timedelta(minutes=50),end,rolling_warnings=warnings)
        self.assertTrue(warnings)
        self.assertTrue(any(w.get('counterDepthMm')==.5 for w in warnings))

    def test_old_midnight_counter_reset_is_identified_without_zero_filling(self):
        rows,start=self.fixture()
        midnight=start+timedelta(minutes=60)
        rows[midnight]['fifteenMinuteMm']=None;rows[midnight]['sixtyMinuteMm']=None
        rows[midnight+timedelta(minutes=1)]['fifteenMinuteMm']=Decimal(0)
        rows[midnight+timedelta(minutes=1)]['sixtyMinuteMm']=Decimal(0)
        with self.assertRaises(RainfallQualityError):
            normalized(rows,start+timedelta(minutes=50),start+timedelta(minutes=180))
        warnings=[]
        values=normalized(rows,start+timedelta(minutes=50),start+timedelta(minutes=180),rolling_warnings=warnings)
        self.assertEqual(sum(v['depthMm'] for v in values),10)
        self.assertTrue(any(w.get('midnightResetInferred') for w in warnings))

    def test_counter_revision_requires_observed_rolling_rainfall(self):
        rows,start=self.fixture()
        for at,row in rows.items():
            if at >= start+timedelta(minutes=65): row['dayMm']-=1
        with self.assertRaises(RainfallQualityError):
            normalized(rows,start+timedelta(minutes=50),start+timedelta(minutes=180))
        warnings=[]
        values=normalized(rows,start+timedelta(minutes=50),start+timedelta(minutes=180),rolling_warnings=warnings)
        self.assertEqual(sum(v['depthMm'] for v in values),10)
        self.assertTrue(any('counterRevisionMm' in w for w in warnings))

    def test_antecedent_observed_gap_total_is_marked_as_interval_assumption(self):
        rows, start = self.fixture()
        at = start+timedelta(minutes=63)
        del rows[at]
        intervals = []
        values = normalized(rows,start+timedelta(minutes=50),start+timedelta(minutes=180),
                            rolling_warnings=[],interval_averages=intervals)
        self.assertEqual(sum(v['depthMm'] for v in values),10)
        self.assertEqual(intervals[0]['minutes'],2)
        self.assertEqual(intervals[0]['totalMm'],1)
        filled = next(v for v in values if v['end']==at.isoformat())
        self.assertEqual(filled['method'],'OBSERVED_INTERVAL_MEAN_ASSUMPTION')
        self.assertNotEqual(filled['method'],'DAILY_DIFFERENCE')
        with self.assertRaises(RainfallQualityError):
            normalized(rows,start+timedelta(minutes=50),start+timedelta(minutes=180))


if __name__ == '__main__':
    unittest.main()
