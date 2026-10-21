"""대회 마감 경계·초 단위 설치·음수 기여 보존 검사."""
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from waterleague_sim.competition_scores import period_score, publish

class CompetitionScoreTests(unittest.TestCase):
    def test_close_boundary_keeps_signed_score_and_partial_first_minute(self):
        start = datetime(2026, 10, 18, 23, 59, 17, tzinfo=timezone.utc)
        boundary = start.replace(second=0)+timedelta(minutes=1)
        frames = [{'at':boundary.isoformat(), 'cumulativeM3': '-0.1234567894'},
                  {'at':(boundary+timedelta(minutes=1)).isoformat(), 'cumulativeM3': 999}]
        self.assertEqual(period_score(frames, start, boundary), (Decimal('-0.123456789'), 43, boundary))
        self.assertIsNone(period_score(frames, start, start.replace(second=0)))
        with self.assertRaisesRegex(ValueError, 'BOUNDARY_INVALID'):
            period_score(frames, start, start)
        with self.assertRaisesRegex(ValueError, 'FRAME_INVALID'):
            period_score([frames[0],frames[0]],start,boundary)
        with self.assertRaisesRegex(ValueError, 'SCORE_INVALID'):
            period_score([{'at':boundary.isoformat(),'cumulativeM3':'NaN'}],start,boundary)

    def test_publisher_uses_same_job_context_and_cuts_off_at_close(self):
        start=datetime(2026,10,19,tzinfo=timezone.utc); end=start+timedelta(minutes=2)
        class Connection:
            def __init__(self): self.writes=[]
            def execute(self,query,args):
                self.writes.append((query,args)); return self
            def fetchall(self): return [{'id':'competition','closes_at':end-timedelta(minutes=1)}]
        conn=Connection()
        job={'id':'job','end':end,'score_context':{'sha256':'context','policySha256':'policy'},
             'installation':{'id':'installation','owner_id':'owner','physics_policy':'INSTALLATION_SECOND_V2','installed_at':start,'district_id':'11680','facility_type':'RAIN_GARDEN'}}
        publish(conn,job,[{'at':(start+timedelta(minutes=1)).isoformat(),'cumulativeM3':3}, {'at':end.isoformat(),'cumulativeM3':4}])
        self.assertEqual(conn.writes[1][1],('competition','installation','owner',Decimal('3.000000000'),60,end-timedelta(minutes=1),'context','policy','job'))
