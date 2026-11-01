"""말단 결측 판별과 원 임대·종료 구간 보존 검증."""
import json
import hashlib
import tempfile
from unittest.mock import patch
import os
import sys
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from weekly_settlement import missing_suffix, claim, register_missing_suffix


class MissingSuffixTests(unittest.TestCase):
    def setUp(self):
        self.start=datetime(2026,10,31,12,tzinfo=timezone.utc)
        self.end=self.start+timedelta(minutes=10)
    def rows(self, minutes):
        return [{'end':(self.start+timedelta(minutes=n)).isoformat()} for n in minutes]
    def test_preserves_valid_prefix_and_accepts_only_a_missing_suffix(self):
        self.assertEqual(missing_suffix(self.rows(range(1,4)),self.start,self.end),self.start+timedelta(minutes=3))
        self.assertEqual(missing_suffix([],self.start,self.end),self.start)
        self.assertIsNone(missing_suffix(self.rows(range(1,11)),self.start,self.end))
    def test_does_not_bridge_interior_missing_state_or_duplicate_timestamps(self):
        self.assertIsNone(missing_suffix(self.rows([1,2,4,5]),self.start,self.end))
        with self.assertRaises(ValueError): missing_suffix(self.rows([1,1]),self.start,self.end)
    def test_rejects_unbounded_or_outside_observations(self):
        with self.assertRaises(ValueError): missing_suffix(self.rows([0]),self.start,self.end)
        with self.assertRaises(ValueError): missing_suffix([],self.start,self.start+timedelta(days=8))


@unittest.skipUnless(os.environ.get('WL_WORKER_TEST_DSN'),'격리 PostgreSQL 필요')
class SettlementQueueTests(unittest.TestCase):
    def test_caps_only_confirmed_suffix_and_does_not_starve_other_installations(self):
        import psycopg
        from psycopg.rows import dict_row
        with psycopg.connect(os.environ['WL_WORKER_TEST_DSN'],autocommit=True,row_factory=dict_row) as db:
            with db.transaction(force_rollback=True):
                row=db.execute('SELECT * FROM shared_installations LIMIT 1').fetchone()
                self.assertIsNotNone(row)
                db.execute('UPDATE shared_installations SET source_retired_at=clock_timestamp()')
                end=datetime.now(timezone.utc).replace(hour=15,minute=0,second=0,microsecond=0)
                end-=timedelta(days=(end.weekday()+1)%7+14)
                cut=end-timedelta(minutes=5)
                target=dict(row)|{'id':str(uuid.uuid4()),'installed_at':end-timedelta(minutes=10),
                    'removed_at':end,'season_ends_at':end,'source_retired_at':None,
                    'physics_policy':'INSTALLATION_SECOND_V2','occupied_site':None,'competition_id':None}
                db.execute('INSERT INTO shared_installations SELECT * FROM json_populate_record(NULL::shared_installations,%s::json)',(json.dumps(target,default=str),))
                fixture=b'controlled-isolated-observation-fixture'
                sha=hashlib.sha256(fixture).hexdigest()
                rain={'observations':[{'end':(end-timedelta(minutes=10)+timedelta(minutes=n)).isoformat()} for n in range(1,6)]}
                def fetcher(*args,**kwargs): return rain,[(fixture,{'sha256':sha})]
                with tempfile.TemporaryDirectory() as directory, patch('weekly_settlement.resolve',return_value=(None,'409','중랑')):
                    self.assertTrue(register_missing_suffix(db,{'installation':target,'previous':None,'start':end-timedelta(minutes=10)},Path(directory),fetcher))
                    evidence=db.execute('SELECT id,evidence_sha256 FROM weekly_observation_exclusions WHERE installation_id=%s',(target['id'],)).fetchone()
                    raw=(Path(directory)/'weekly-exclusions'/str(evidence['id'])/'evidence.json').read_bytes()
                    self.assertEqual(hashlib.sha256(raw).hexdigest(),evidence['evidence_sha256'])
                job=claim(db)
                self.assertEqual(str(job['installation']['id']),target['id'])
                self.assertEqual(job['end'],cut)
                persisted=db.execute('SELECT requested_through FROM shared_physics_jobs WHERE id=%s',(job['id'],)).fetchone()
                self.assertEqual(persisted['requested_through'],cut)
                db.execute("UPDATE shared_physics_jobs SET state='SUCCEEDED',finished_at=clock_timestamp(),lease_until=NULL,result='{}',input_hash=%s WHERE id=%s",('a'*64,job['id']))
                other=target|{'id':str(uuid.uuid4())}
                db.execute('INSERT INTO shared_installations SELECT * FROM json_populate_record(NULL::shared_installations,%s::json)',(json.dumps(other,default=str),))
                following=claim(db)
                self.assertEqual(str(following['installation']['id']),other['id'])
                self.assertEqual(following['end'],end)
