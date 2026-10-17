"""전용 임시 DB에서 공동 시설 임대·재현 입력 연속성 검사. 합성 강우는 시험 전용."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import threading
import uuid
import unittest
from unittest.mock import patch

import test_worker_queue as queue_fixture
from waterleague_sim import shared_physics as physics
from waterleague_sim.shared_model import catalog


class SharedPhysicsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        queue_fixture.WorkerQueueTests.setUpClass.__func__(cls)

    connection = queue_fixture.WorkerQueueTests.connection

    def setUp(self):
        queue_fixture.WorkerQueueTests.setUp(self)
        self.installation = uuid.uuid4()
        model_hash = catalog()[0]['2419953']['defaultModelHash']
        start = datetime.now(timezone.utc).replace(second=0, microsecond=0)-timedelta(minutes=10)
        self.conn.execute("""INSERT INTO shared_installations(id,occupied_site,district_id,cell_id,
            owner_id,model_hash,facility_type,area_m2,cost,installed_at)
            VALUES(%s,'2419953:G1','2419953','G1',%s,%s,'RAIN_GARDEN',10,1000000,%s)""",
            (self.installation, self.owner, model_hash, start))
        evaporation = patch.object(physics, 'observed_evaporation', side_effect=self.evaporation)
        evaporation.start()
        self.addCleanup(evaporation.stop)

    def evaporation(self, start, end, key):
        raw = b'SYNTHETIC_WEATHER_TEST_ONLY\n'; sha = physics.digest(raw)
        return {'method': 'SYNTHETIC_TEST_ONLY', 'sourceHashes': [sha], 'hours': [],
                'ratesMmDay': [2]*int((end-start).total_seconds()/60)}, [(raw, {'sha256': sha, 'purpose': 'SYNTHETIC_TEST_ONLY'})]

    def test_atomic_claim_and_expired_result_fencing(self):
        barrier = threading.Barrier(2)
        def attempt():
            with self.connection() as db:
                barrier.wait()
                return physics.claim(db)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: attempt(), range(2)))
        jobs = [v for v in results if v is not None]
        self.assertEqual(len(jobs), 1)
        old = jobs[0]
        self.conn.execute("UPDATE shared_physics_jobs SET lease_until=now()-interval '1 second',created_at=now()-interval '61 seconds' WHERE id=%s", (old['id'],))
        new = physics.claim(self.conn)
        self.assertIsNotNone(new)
        self.assertNotEqual(old['lease_token'], new['lease_token'])
        self.assertFalse(physics.finish(self.conn, old, {'stale': True}, 'a'*64, None))
        self.assertTrue(physics.finish(self.conn, new, None, None, 'KMA_UNAVAILABLE'))
        self.assertEqual(self.conn.execute('SELECT error_code FROM shared_physics_jobs WHERE id=%s', (old['id'],)).fetchone()['error_code'], 'LIVE_LEASE_EXPIRED')

    def forcing(self, station, start, end, key):
        def rows(begin, finish):
            return [{'end': (begin+timedelta(minutes=i)).isoformat(), 'depthMm': .3,
                     'method': 'SYNTHETIC_TEST_ONLY', 'weather': {}}
                    for i in range(1, int((finish-begin).total_seconds()/60)+1)]
        raw = ('SYNTHETIC_TEST_ONLY '+start.isoformat()+'\n').encode()
        sha = physics.digest(raw)
        return {'stationId': station, 'start': start.isoformat(), 'end': end.isoformat(),
            'intervalSeconds': 60, 'observations': rows(start, end),
            'overlapObservations': rows(start-timedelta(minutes=60), start),
            'sourceHashes': [sha], 'evidence': 'SYNTHETIC_TEST_ONLY'}, [(raw, {'sha256': sha, 'purpose': 'SYNTHETIC_TEST_ONLY'})]

    def test_new_footprint_boundary_runs_without_unverified_external_inflow(self):
        new_hash=catalog()[1]['2419953']['sha256']
        self.conn.execute('UPDATE shared_installations SET model_hash=%s,area_m2=25 WHERE id=%s',(new_hash,self.installation))
        job=physics.claim(self.conn)
        with tempfile.TemporaryDirectory() as root, patch.object(physics,'observed_forcing',side_effect=self.forcing):
            self.assertTrue(physics.process(self.conn,job,root))
            row=self.conn.execute('SELECT * FROM shared_physics_jobs WHERE id=%s',(job['id'],)).fetchone()
            self.assertEqual(row['state'],'SUCCEEDED',row['error_code'])
            result=json.loads(row['result'])
            self.assertEqual(result['inflowPolicy'],'DIRECT_RAINFALL_ONLY')
            self.assertEqual(result['areaLimitBasis'],'PUBLIC_FOOTPRINT_GEOMETRY')

    def test_real_child_replays_preserved_input_and_refuses_revised_overlap(self):
        first = physics.claim(self.conn)
        full_end = first['end']
        first['end'] -= timedelta(minutes=3)
        self.conn.execute('UPDATE shared_physics_jobs SET requested_through=%s WHERE id=%s', (first['end'], first['id']))
        with tempfile.TemporaryDirectory() as root, patch.object(physics, 'observed_forcing', side_effect=self.forcing):
            self.assertTrue(physics.process(self.conn, first, root))
            row = self.conn.execute('SELECT * FROM shared_physics_jobs WHERE id=%s', (first['id'],)).fetchone()
            self.assertEqual(row['state'], 'SUCCEEDED', row['error_code'])
            self.conn.execute("UPDATE shared_physics_jobs SET created_at=now()-interval '61 seconds' WHERE id=%s", (first['id'],))
            second = physics.claim(self.conn)
            self.assertEqual(second['start'], first['start'])
            self.assertGreaterEqual(second['end'], full_end)
            self.assertTrue(physics.process(self.conn, second, root))
            row = self.conn.execute('SELECT * FROM shared_physics_jobs WHERE id=%s', (second['id'],)).fetchone()
            self.assertEqual(row['state'], 'SUCCEEDED', row['error_code'])
            def artifact(job, name):
                return json.loads((Path(root)/'shared-physics'/str(job['id'])/str(job['lease_token'])/name).read_text())
            prefix = artifact(first, 'result.json')['strategy']['samples']
            self.assertEqual(prefix, artifact(second, 'result.json')['strategy']['samples'][:len(prefix)])
            self.assertEqual(artifact(second, 'forcing.json')['previousInput']['jobId'], str(first['id']))
            first_directory=Path(root)/'shared-physics'/str(first['id'])/str(first['lease_token'])
            first_source=artifact(first,'forcing.json')['sourceHashes'][0]+'.txt'
            self.assertEqual((first_directory/first_source).stat().st_ino,
                (Path(root)/'shared-physics'/str(second['id'])/str(second['lease_token'])/first_source).stat().st_ino)
            self.assertEqual((first_directory/first_source).stat().st_ino,
                (Path(root)/'observation-sources'/first_source).stat().st_ino)
            directory=Path(root)/'shared-physics'/str(second['id'])/str(second['lease_token'])
            self.assertEqual(row['artifact_manifest_hash'],physics.digest((directory/'manifest.json').read_bytes()))
            forcing=artifact(second,'forcing.json')
            self.assertTrue(forcing['sourceArchive']['complete'])
            for sha in forcing['sourceHashes']+forcing['evaporation']['sourceHashes']:
                self.assertEqual(physics.digest((directory/(sha+'.txt')).read_bytes()),sha)
            score=self.conn.execute('SELECT SUM(score_m3) AS score,SUM(evaluated_minutes) AS minutes FROM shared_weekly_scores WHERE installation_id=%s',(self.installation,)).fetchone()
            self.assertEqual(score['minutes'],len(artifact(second,'result.json')['contribution']))
            self.assertAlmostEqual(float(score['score']),artifact(second,'result.json')['contribution'][-1]['cumulativeM3'],places=8)
            with self.conn.transaction():
                from waterleague_sim.weekly import aggregate,publish
                # 동일 결과의 재게시에도 분 수와 점수가 늘어나지 않는다.
                replay=aggregate(artifact(second,'result.json')['contribution'],second['start'],second['end'],second['end'])
                publish(self.conn,second,replay)
            self.assertEqual(self.conn.execute('SELECT SUM(evaluated_minutes) AS n FROM shared_weekly_scores WHERE installation_id=%s',(self.installation,)).fetchone()['n'],score['minutes'])
            # 과거 분량의 수정은 재현 입력을 바꾸지 않고 새 결과 게시를 차단한다.
            third = dict(second, id=uuid.uuid4(), lease_token=uuid.uuid4(), previous=row,
                         end=second['end']+timedelta(minutes=1))
            self.conn.execute("""INSERT INTO shared_physics_jobs(id,installation_id,simulation_start,
                requested_through,state,lease_token,lease_until,created_at)
                VALUES(%s,%s,%s,%s,'RUNNING',%s,now()+interval '240 seconds',now())""",
                (third['id'], self.installation, third['start'], third['end'], third['lease_token']))
            def revised(*args):
                forcing, source = self.forcing(*args)
                forcing['overlapObservations'][-1]['depthMm'] = .4
                return forcing, source
            with patch.object(physics, 'observed_forcing', side_effect=revised):
                physics.process(self.conn, third, root)
            failure = self.conn.execute('SELECT * FROM shared_physics_jobs WHERE id=%s', (third['id'],)).fetchone()
            self.assertEqual(failure['state'], 'FAILED')
            self.assertEqual(failure['error_code'], 'AWS_PREVIOUS_INTERVAL_REVISED')

    def test_weather_hour_reuse_preserves_state_with_new_rainfall_queries(self):
        start=datetime.now(timezone.utc).replace(minute=10,second=0,microsecond=0)-timedelta(hours=1)
        self.conn.execute('UPDATE shared_installations SET installed_at=%s WHERE id=%s',(start,self.installation))
        first=physics.claim(self.conn);first['end']=start+timedelta(minutes=5)
        self.conn.execute('UPDATE shared_physics_jobs SET requested_through=%s WHERE id=%s',(first['end'],first['id']))
        def hourly_input(begin,end,key):
            value,sources=self.evaporation(begin,end,key)
            return value | {'method':'FAO56_HOURLY_LAGGED_ASOS_AWS_V1','evidence':'SYNTHETIC_TEST_ONLY',
                'hours':[{'observationEnd':begin.replace(minute=0).isoformat(),'appliesFrom':begin.isoformat(),
                          'appliesUntil':end.isoformat(),'referenceEtMmHour':2/24}]},sources
        with tempfile.TemporaryDirectory() as root, patch.object(physics,'observed_forcing',side_effect=self.forcing) as rain, patch.object(physics,'observed_evaporation',side_effect=hourly_input) as weather:
            physics.process(self.conn,first,root)
            first_row=self.conn.execute('SELECT * FROM shared_physics_jobs WHERE id=%s',(first['id'],)).fetchone()
            self.assertEqual(first_row['state'],'SUCCEEDED',first_row['error_code'])
            self.conn.execute("UPDATE shared_physics_jobs SET created_at=now()-interval '61 seconds' WHERE id=%s",(first['id'],))
            second=physics.claim(self.conn);self.assertIsNotNone(second)
            second['end']=start+timedelta(minutes=6)
            self.conn.execute('UPDATE shared_physics_jobs SET requested_through=%s WHERE id=%s',(second['end'],second['id']))
            physics.process(self.conn,second,root)
            row=self.conn.execute('SELECT * FROM shared_physics_jobs WHERE id=%s',(second['id'],)).fetchone()
            self.assertEqual(row['state'],'SUCCEEDED',row['error_code'])
            self.assertEqual(rain.call_count,2)
            self.assertEqual(weather.call_count,1)
            forcing=json.loads((Path(root)/'shared-physics'/str(second['id'])/str(second['lease_token'])/'forcing.json').read_text())
            self.assertEqual(forcing['evaporation']['ratesMmDay'],[2]*6)
            self.assertEqual(len(forcing['evaporation']['hours']),1)
            self.assertTrue(forcing['sourceArchive']['complete'])
