"""한국시간 주 경계·음수 기여·반올림 누적 오차 검사."""
import unittest
from datetime import datetime, timedelta
from decimal import Decimal
from waterleague_sim.weekly import aggregate, KST


class WeeklyTests(unittest.TestCase):
    def test_week_boundary_signed_increment_and_prefix(self):
        start=datetime(2026,10,18,23,58,tzinfo=KST)
        values=[1.1234567894, .75, .65, .9]
        frames=[{'at':(start+timedelta(minutes=i+1)).isoformat(),'cumulativeM3':v} for i,v in enumerate(values)]
        weeks=aggregate(frames,start,start+timedelta(minutes=4),start+timedelta(minutes=2))
        a,b=weeks.values()
        self.assertEqual(a['score'],Decimal('.750000000'))
        self.assertEqual(a['prefixScore'],a['score'])
        self.assertEqual(a['minutes'],2)
        self.assertEqual(b['score'],Decimal('.150000000'))
        self.assertEqual(b['prefixMinutes'],0)
        self.assertEqual(sum(v['score'] for v in weeks.values()),Decimal('.900000000'))

    def test_gap_or_nonfinite_input_is_rejected(self):
        start=datetime(2026,10,18,tzinfo=KST)
        for frames in ([{'at':(start+timedelta(minutes=2)).isoformat(),'cumulativeM3':1}],
                       [{'at':(start+timedelta(minutes=1)).isoformat(),'cumulativeM3':float('nan')}]):
            with self.assertRaisesRegex(ValueError,'LIVE_WEEKLY_INPUT_INVALID'):
                aggregate(frames,start,start+timedelta(minutes=2),start)

    def test_partial_first_minute_and_korean_week_boundary_keep_actual_seconds(self):
        from waterleague_sim.weekly import SECOND_RULE
        start=datetime(2026,10,18,23,59,17,tzinfo=KST)
        boundary=start.replace(second=0)+timedelta(minutes=1)
        frames=[{'at':boundary.isoformat(),'cumulativeM3':.75},
                {'at':(boundary+timedelta(minutes=1)).isoformat(),'cumulativeM3':.5}]
        old,new=aggregate(frames,start,boundary+timedelta(minutes=1),boundary,rule=SECOND_RULE).values()
        self.assertEqual((old['seconds'],old['prefixSeconds'],old['score']),(43,43,Decimal('.75')))
        self.assertEqual((new['seconds'],new['prefixSeconds'],new['score']),(60,0,Decimal('-.25')))
        self.assertEqual(old['minutes'],1)
        with self.assertRaisesRegex(ValueError,'LIVE_WEEKLY_INPUT_INVALID'):
            aggregate(frames,start,boundary+timedelta(minutes=1),boundary)

    def test_partial_minute_gap_and_subsecond_clock_refused(self):
        from waterleague_sim.weekly import SECOND_RULE
        start=datetime(2026,10,19,0,0,59,tzinfo=KST)
        end=start.replace(second=0)+timedelta(minutes=1)
        frame={'at':end.isoformat(),'cumulativeM3':-.01}
        value=next(iter(aggregate([frame],start,end,start,rule=SECOND_RULE).values()))
        self.assertEqual(value['seconds'],1)
        for begin in (start+timedelta(microseconds=1),start-timedelta(minutes=1)):
            with self.assertRaisesRegex(ValueError,'LIVE_WEEKLY_INPUT_INVALID'):
                aggregate([frame],begin,end,begin,rule=SECOND_RULE)
