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
from waterleague_sim import admission
from contextlib import closing
from waterleague_sim.spatial.play_bundle import open_catalog
from native_contract_evidence import verify as verify_contract


class SharedPhysicsTests(unittest.TestCase):
    def reconciliation_fixture(self, root):
        from waterleague_sim.evaluation import score_policy as policy
        self.conn.execute("UPDATE shared_installations SET physics_policy=%s,installed_at=installed_at+interval '17 seconds',season_ends_at=installed_at+interval '7 days',occupied_site=owner_id::text||':'||district_id||':'||cell_id WHERE id=%s",
                          (physics.SECOND_POLICY, self.installation))
        first = physics.claim(self.conn)
        with patch.object(physics, 'observed_forcing', side_effect=self.forcing):
            self.assertTrue(physics.process(self.conn, first, root))
        stored = self.conn.execute('SELECT * FROM shared_physics_jobs WHERE id=%s', (first['id'],)).fetchone()
        self.assertEqual(stored['state'], 'SUCCEEDED', stored['error_code'])
        directory = Path(root)/'shared-physics'/str(first['id'])/str(first['lease_token'])
        archived = json.loads((directory/'score-policy.json').read_bytes())
        archived['files']['simulation/waterleague_sim/ingestion/live.py'] = 'b'*64
        (directory/'score-policy.json').write_bytes(policy.encode(archived))
        context = first['score_context'] | {'policySha256': physics.digest((directory/'score-policy.json').read_bytes())}
        context['sha256'] = policy.digest(policy.encode({k:v for k,v in context.items() if k!='sha256'}))
        for name in ('request.json', 'result.json'):
            value = json.loads((directory/name).read_bytes()) | {'scoreContext': context}
            (directory/name).write_bytes(physics.encode(value))
        (directory/'score-context.json').write_bytes(policy.encode(context))
        manifest = json.loads((directory/'manifest.json').read_bytes())
        for name in ('request.json','result.json','score-policy.json','score-context.json'):
            manifest[name] = physics.digest((directory/name).read_bytes())
        (directory/'manifest.json').write_bytes(physics.encode(manifest))
        public = json.loads(stored['result']) | {'scoreContext': context}
        self.conn.execute('UPDATE shared_physics_jobs SET result=%s,input_hash=%s,artifact_manifest_hash=%s WHERE id=%s',
            (json.dumps(public), physics.digest((directory/'request.json').read_bytes()),
             physics.digest((directory/'manifest.json').read_bytes()), first['id']))
        self.conn.execute('UPDATE shared_weekly_scores SET score_policy_sha256=%s,comparison_group_hash=%s WHERE installation_id=%s',
            (context['policySha256'],context['sha256'],self.installation))
        self.conn.execute('UPDATE shared_installations SET season_ends_at=%s WHERE id=%s', (first['end'], self.installation))
        return directory

    def test_offline_reconciliation_preserves_actual_states_and_scores_without_new_weather(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location('reconcile_weekly', physics.ROOT/'deploy/reconcile_weekly.py')
        reconcile = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(reconcile)
        with tempfile.TemporaryDirectory() as root:
            self.reconciliation_fixture(root)
            before = self.conn.execute('SELECT * FROM shared_weekly_scores WHERE installation_id=%s', (self.installation,)).fetchall()
            job = reconcile.claim(self.conn)
            self.assertIsNotNone(job)
            self.assertEqual(job['end'], job['previous']['requested_through'])
            self.assertIsNone(physics.claim(self.conn))
            with patch.object(physics, 'observed_forcing', side_effect=AssertionError('새 관측 호출 금지')):
                self.assertTrue(reconcile.replay(self.conn, job, root))
            after = self.conn.execute('SELECT * FROM shared_weekly_scores WHERE installation_id=%s', (self.installation,)).fetchall()
            for old, new in zip(before, after, strict=True):
                for key in ('score_m3','evaluated_seconds','evaluated_minutes','evaluated_through','rule_version'):
                    self.assertEqual(old[key], new[key])
                self.assertEqual(new['score_policy_sha256'], job['score_context']['policySha256'])
                self.assertNotEqual(old['comparison_group_hash'], new['comparison_group_hash'])
            self.assertIsNone(reconcile.claim(self.conn))

    def test_offline_reconciliation_rejects_damaged_archive_without_publishing(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location('reconcile_weekly', physics.ROOT/'deploy/reconcile_weekly.py')
        reconcile = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(reconcile)
        with tempfile.TemporaryDirectory() as root:
            directory = self.reconciliation_fixture(root)
            before = self.conn.execute('SELECT * FROM shared_weekly_scores WHERE installation_id=%s', (self.installation,)).fetchall()
            (directory/'forcing.json').write_bytes(b'{}')
            job = reconcile.claim(self.conn)
            self.assertFalse(reconcile.replay(self.conn, job, root))
            self.assertEqual(before, self.conn.execute('SELECT * FROM shared_weekly_scores WHERE installation_id=%s', (self.installation,)).fetchall())
            self.assertIsNone(reconcile.claim(self.conn))

    @classmethod
    def setUpClass(cls):
        queue_fixture.WorkerQueueTests.setUpClass.__func__(cls)
        cls.native = open_catalog()
        cls.cell = cls.native.require('C0000fe65db41b6f0c5e9fa6d', '11290')
        policy = json.loads((physics.ROOT / 'backend/src/main/resources/infrastructure/native-v1/associations.json').read_bytes())
        cls.asset_policy = {key: policy[key] for key in
            ('version', 'sourceSha256', 'siteCatalogSha256', 'scope', 'historicalExistenceVerified')}
        cls.asset_policy.update(sha256=admission.NATIVE_SHA256, confirmedFootprintCount=0)
        with closing(cls.native.connection()) as db:
            cls.second_cell = db.execute("SELECT id FROM sites WHERE district_id='11290' AND allowed_mask&1=1 AND id<>? ORDER BY id LIMIT 1", (cls.cell['id'],)).fetchone()[0]

    connection = queue_fixture.WorkerQueueTests.connection

    def setUp(self):
        queue_fixture.WorkerQueueTests.setUp(self)
        self.installation = uuid.uuid4()
        model_hash = self.native.sha256
        start = datetime.now(timezone.utc).replace(second=0, microsecond=0)-timedelta(minutes=10)
        self.conn.execute("""INSERT INTO shared_installations(id,occupied_site,district_id,cell_id,
            owner_id,model_hash,facility_type,area_m2,cost,installed_at,admission_snapshot)
            VALUES(%s,%s,'11290',%s,%s,%s,'RAIN_GARDEN',10,5600000,%s,%s)""",
            (self.installation, '11290:'+self.cell['id'], self.cell['id'], self.owner, model_hash, start,
             json.dumps(self.asset_policy)))
        evaporation = patch.object(physics, 'observed_evaporation', side_effect=self.evaporation)
        evaporation.start()
        self.addCleanup(evaporation.stop)
        from waterleague_sim.ingestion import antecedent
        warmup = patch.object(antecedent, 'fetch', side_effect=self.antecedent)
        self.warmup_fetch = warmup.start()
        self.addCleanup(warmup.stop)

    def antecedent(self, station, end, key, heartbeat=None):
        if heartbeat is not None: heartbeat()
        from waterleague_sim.engine.initialization import MINUTES
        start = end-timedelta(days=7)
        rain, sources = self.forcing(station, start, end, key)
        pet, weather = self.evaporation(start, end, key)
        return {'rainfall': {k: rain[k] for k in ('start','end','stationId','intervalSeconds','sourceHashes','evidence')}
            | {'depthsMm': [0]*(MINUTES-60)+[.3]*60}, 'evaporation': pet}, sources+weather

    def evaporation(self, start, end, key, heartbeat=None):
        if heartbeat is not None: heartbeat()
        raw = b'SYNTHETIC_WEATHER_TEST_ONLY\n'; sha = physics.digest(raw)
        return {'method': 'SYNTHETIC_TEST_ONLY', 'sourceHashes': [sha], 'hours': [],
                'ratesMmDay': [2]*int((end-start).total_seconds()/60)}, [(raw, {'sha256': sha, 'purpose': 'SYNTHETIC_TEST_ONLY'})]

    def test_expired_season_runs_missing_minutes_then_stops_without_reset_or_double_score(self):
        start = self.conn.execute('SELECT installed_at FROM shared_installations WHERE id=%s', (self.installation,)).fetchone()['installed_at']
        end = start + timedelta(minutes=4)
        self.conn.execute("UPDATE shared_installations SET season_ends_at=%s,occupied_site=%s WHERE id=%s",
                          (end, str(self.owner)+':11290:'+self.cell['id'], self.installation))
        job=physics.claim(self.conn)
        self.assertEqual(job['end'],end)
        self.assertEqual(job['start'],start)
        with tempfile.TemporaryDirectory() as root, patch.object(physics,'observed_forcing',side_effect=self.forcing):
            self.assertTrue(physics.process(self.conn,job,root))
            row=self.conn.execute('SELECT * FROM shared_physics_jobs WHERE id=%s',(job['id'],)).fetchone()
            self.assertEqual(row['state'],'SUCCEEDED',row['error_code'])
            path = Path(root) / 'shared-physics' / str(job['id']) / str(job['lease_token'])
            verify_contract(self, path)
            self.assertEqual(json.loads(row['result'])['designContract'],
                             json.loads((path / 'result.json').read_bytes())['designContract'])
            score=self.conn.execute('SELECT SUM(evaluated_minutes) AS minutes FROM shared_weekly_scores WHERE installation_id=%s',(self.installation,)).fetchone()
            self.assertEqual(score['minutes'],4)
            self.conn.execute("UPDATE shared_physics_jobs SET created_at=now()-interval '61 seconds' WHERE id=%s",(job['id'],))
            self.assertIsNone(physics.claim(self.conn))
            self.conn.execute('UPDATE shared_installations SET removed_at=season_ends_at,occupied_site=NULL WHERE id=%s',(self.installation,))
            self.assertIsNone(physics.claim(self.conn))

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
        physics.renew(self.conn,old)
        with self.assertRaisesRegex(ValueError,'LIVE_LEASE_LOST'):
            physics.renew(self.conn,dict(old,lease_token=uuid.uuid4()))
        self.conn.execute("UPDATE shared_physics_jobs SET lease_until=now()-interval '1 second',created_at=now()-interval '61 seconds' WHERE id=%s", (old['id'],))
        with self.assertRaisesRegex(ValueError,'LIVE_LEASE_LOST'):
            physics.renew(self.conn,old)
        self.assertIsNone(physics.claim(self.conn))
        self.conn.execute("UPDATE shared_physics_jobs SET finished_at=now()-interval '301 seconds' WHERE id=%s", (old['id'],))
        new = physics.claim(self.conn)
        self.assertIsNotNone(new)
        self.assertNotEqual(old['lease_token'], new['lease_token'])
        self.assertFalse(physics.finish(self.conn, old, {'stale': True}, 'a'*64, None))
        self.assertTrue(physics.finish(self.conn, new, None, None, 'KMA_UNAVAILABLE'))
        self.assertEqual(self.conn.execute('SELECT error_code FROM shared_physics_jobs WHERE id=%s', (old['id'],)).fetchone()['error_code'], 'LIVE_LEASE_EXPIRED')

    def test_long_failed_fetch_waits_after_finish_without_delaying_other_installations(self):
        job = physics.claim(self.conn)
        self.conn.execute("UPDATE shared_physics_jobs SET created_at=now()-interval '20 minutes' WHERE id=%s", (job['id'],))
        self.assertTrue(physics.finish(self.conn,job,None,None,'AWS_REQUIRED_MINUTE_MISSING'))
        self.assertIsNone(physics.claim(self.conn))
        second = uuid.uuid4()
        self.conn.execute("""INSERT INTO shared_installations(id,occupied_site,district_id,cell_id,
            owner_id,model_hash,facility_type,area_m2,cost,installed_at)
            SELECT %s,%s,district_id,%s,owner_id,model_hash,facility_type,area_m2,cost,installed_at
            FROM shared_installations WHERE id=%s""", (second,'11290:'+self.second_cell,self.second_cell,self.installation))
        ready = physics.claim(self.conn)
        self.assertEqual(ready['installation']['id'],second)
        self.conn.execute("UPDATE shared_physics_jobs SET finished_at=now()-interval '301 seconds' WHERE id=%s", (job['id'],))
        retry = physics.claim(self.conn)
        self.assertEqual(retry['installation']['id'],self.installation)

    def test_renewal_wait_crossing_deadline_does_not_revive_weekly_job(self):
        job = physics.claim(self.conn)
        self.conn.execute("UPDATE shared_physics_jobs SET lease_until=clock_timestamp()+interval '300 milliseconds' WHERE id=%s",
                          (job['id'],))
        started = threading.Event()
        def renew():
            with self.connection() as connection:
                started.set()
                physics.renew(connection, job)
        with self.connection() as blocker, ThreadPoolExecutor(max_workers=1) as pool:
            with blocker.transaction():
                blocker.execute('SELECT id FROM shared_physics_jobs WHERE id=%s FOR UPDATE', (job['id'],))
                pending = pool.submit(renew)
                self.assertTrue(started.wait(timeout=2))
                with self.assertRaises(TimeoutError):
                    pending.result(timeout=.5)
            with self.assertRaisesRegex(ValueError, 'LIVE_LEASE_LOST'):
                pending.result(timeout=3)
        row = self.conn.execute('SELECT * FROM shared_physics_jobs WHERE id=%s', (job['id'],)).fetchone()
        self.assertLessEqual(row['lease_until'], datetime.now(timezone.utc))
        self.assertIsNone(row['result'])
        self.assertFalse(physics.finish(self.conn, job, {'stale': True}, 'a'*64, None))

    def forcing(self, station, start, end, key, heartbeat=None, share_ranges=False):
        if heartbeat is not None: heartbeat()
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
        new_hash=self.native.sha256
        self.conn.execute('UPDATE shared_installations SET model_hash=%s,area_m2=25 WHERE id=%s',(new_hash,self.installation))
        job=physics.claim(self.conn)
        with tempfile.TemporaryDirectory() as root, patch.object(physics,'observed_forcing',side_effect=self.forcing):
            self.assertTrue(physics.process(self.conn,job,root))
            row=self.conn.execute('SELECT * FROM shared_physics_jobs WHERE id=%s',(job['id'],)).fetchone()
            self.assertEqual(row['state'],'SUCCEEDED',row['error_code'])
            result=json.loads(row['result'])
            self.assertEqual(result['inflowPolicy'],'DIRECT_RAINFALL_ONLY')
            self.assertEqual(result['areaLimitBasis'],'PUBLIC_NATIVE_DESIGN_GEOMETRY')
            self.assertEqual(result['facilityDesign']['nativeSoilBoundary']['method'], 'RG_NATIVE_SOIL_SEEPAGE_V1')
            self.assertEqual(result['initialState'],'OBSERVED_7_DAY_CONTINUOUS_SPINUP_V1')
            self.assertTrue(result['initialization']['scoreExcludesWarmup'])
            self.assertEqual(result['facilityDesign']['profile']['id'],'EPA_RG_610_V1')
            saved = Path(root)/'shared-physics'/str(job['id'])/str(job['lease_token'])
            calculation = json.loads((saved/'result.json').read_text())
            self.assertEqual(len(calculation['contribution']), int((job['end']-job['start']).total_seconds()/60))

    def test_real_child_replays_preserved_input_and_refuses_revised_overlap(self, policy_change=False):
        first = physics.claim(self.conn)
        full_end = first['end']
        first['end'] -= timedelta(minutes=3)
        self.conn.execute('UPDATE shared_physics_jobs SET requested_through=%s WHERE id=%s', (first['end'], first['id']))
        with tempfile.TemporaryDirectory() as root, patch.object(physics, 'observed_forcing', side_effect=self.forcing):
            self.assertTrue(physics.process(self.conn, first, root))
            row = self.conn.execute('SELECT * FROM shared_physics_jobs WHERE id=%s', (first['id'],)).fetchone()
            self.assertEqual(row['state'], 'SUCCEEDED', row['error_code'])
            if policy_change:
                from waterleague_sim.evaluation import score_policy as policy
                directory = Path(root)/'shared-physics'/str(first['id'])/str(first['lease_token'])
                archived = json.loads((directory/'score-policy.json').read_bytes())
                archived['files']['simulation/waterleague_sim/weekly.py'] = 'b'*64
                (directory/'score-policy.json').write_bytes(policy.encode(archived))
                context = first['score_context'] | {'policySha256': physics.digest((directory/'score-policy.json').read_bytes())}
                context['sha256'] = policy.digest(policy.encode({k:v for k,v in context.items() if k!='sha256'}))
                for name in ('request.json', 'result.json'):
                    value = json.loads((directory/name).read_bytes())
                    value['scoreContext'] = context
                    (directory/name).write_bytes(physics.encode(value))
                (directory/'score-context.json').write_bytes(policy.encode(context))
                manifest = json.loads((directory/'manifest.json').read_bytes())
                for name in ('request.json','result.json','score-policy.json','score-context.json'):
                    manifest[name] = physics.digest((directory/name).read_bytes())
                (directory/'manifest.json').write_bytes(physics.encode(manifest))
                self.conn.execute('UPDATE shared_physics_jobs SET input_hash=%s,artifact_manifest_hash=%s WHERE id=%s',
                    (physics.digest((directory/'request.json').read_bytes()),physics.digest((directory/'manifest.json').read_bytes()),first['id']))
                self.conn.execute('UPDATE shared_weekly_scores SET score_policy_sha256=%s,comparison_group_hash=%s WHERE installation_id=%s',
                    (context['policySha256'],context['sha256'],self.installation))
                self.conn.execute('''INSERT INTO shared_installations(id,occupied_site,district_id,cell_id,
                    owner_id,model_hash,facility_type,area_m2,cost,installed_at)
                    SELECT %s,%s,district_id,%s,owner_id,model_hash,facility_type,area_m2,cost,installed_at
                    FROM shared_installations WHERE id=%s''',
                    (uuid.uuid4(),'11290:'+self.second_cell,self.second_cell,self.installation))
            self.conn.execute("UPDATE shared_physics_jobs SET created_at=now()-interval '61 seconds' WHERE id=%s", (first['id'],))
            if first['installation'].get('physics_policy') == physics.SECOND_POLICY:
                self.conn.execute("SET TIME ZONE 'UTC'")
            second = physics.claim(self.conn)
            self.assertEqual(second['installation']['id'], self.installation)
            self.assertEqual(second['start'], first['start'])
            self.assertGreaterEqual(second['end'], full_end)
            self.assertTrue(physics.process(self.conn, second, root))
            row = self.conn.execute('SELECT * FROM shared_physics_jobs WHERE id=%s', (second['id'],)).fetchone()
            self.assertEqual(row['state'], 'SUCCEEDED', row['error_code'])
            if policy_change:
                stored = self.conn.execute('SELECT score_policy_sha256,comparison_group_hash FROM shared_weekly_scores WHERE installation_id=%s', (self.installation,)).fetchone()
                self.assertEqual(stored['score_policy_sha256'], second['score_context']['policySha256'])
                self.assertEqual(stored['comparison_group_hash'], second['score_context']['sha256'])
                self.assertEqual(self.conn.execute("SELECT count(*) n FROM shared_physics_jobs WHERE state='SUCCEEDED' AND installation_id=%s", (self.installation,)).fetchone()['n'], 2)
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
                origin=second['installation']['installed_at'] if second['installation'].get('physics_policy') == physics.SECOND_POLICY else second['start']
                rule=physics.SECOND_RULE if second['installation'].get('physics_policy') == physics.SECOND_POLICY else physics.RULE
                replay=aggregate(artifact(second,'result.json')['contribution'],origin,second['end'],second['end'],rule=rule)
                publish(self.conn,second,replay)
            self.assertEqual(self.conn.execute('SELECT SUM(evaluated_minutes) AS n FROM shared_weekly_scores WHERE installation_id=%s',(self.installation,)).fetchone()['n'],score['minutes'])
            # 과거 분량의 수정은 재현 입력을 바꾸지 않고 새 결과 게시를 차단한다.
            third = dict(second, id=uuid.uuid4(), lease_token=uuid.uuid4(), previous=row,
                         end=second['end']+timedelta(minutes=1))
            self.conn.execute("""INSERT INTO shared_physics_jobs(id,installation_id,simulation_start,
                requested_through,state,lease_token,lease_until,created_at)
                VALUES(%s,%s,%s,%s,'RUNNING',%s,now()+interval '240 seconds',now())""",
                (third['id'], self.installation, third['start'], third['end'], third['lease_token']))
            def revised(*args, **kwargs):
                forcing, source = self.forcing(*args, **kwargs)
                forcing['overlapObservations'][-1]['depthMm'] = .4
                return forcing, source
            with patch.object(physics, 'observed_forcing', side_effect=revised):
                physics.process(self.conn, third, root)
            failure = self.conn.execute('SELECT * FROM shared_physics_jobs WHERE id=%s', (third['id'],)).fetchone()
            self.assertEqual(failure['state'], 'FAILED')
            self.assertEqual(failure['error_code'], 'AWS_PREVIOUS_INTERVAL_REVISED')

    def test_observed_initialization_is_frozen_across_replays(self):
        self.conn.execute('UPDATE shared_installations SET model_hash=%s WHERE id=%s',
                          (self.native.sha256, self.installation))
        self.test_real_child_replays_preserved_input_and_refuses_revised_overlap()
        self.warmup_fetch.assert_called_once()

    def test_code_policy_transition_replays_old_observations_and_preserves_all_scores(self):
        self.test_real_child_replays_preserved_input_and_refuses_revised_overlap(policy_change=True)

    def test_weather_hour_reuse_preserves_state_with_new_rainfall_queries(self):
        start=datetime.now(timezone.utc).replace(minute=10,second=0,microsecond=0)-timedelta(hours=1)
        self.conn.execute('UPDATE shared_installations SET installed_at=%s WHERE id=%s',(start,self.installation))
        first=physics.claim(self.conn);first['end']=start+timedelta(minutes=5)
        self.conn.execute('UPDATE shared_physics_jobs SET requested_through=%s WHERE id=%s',(first['end'],first['id']))
        def hourly_input(begin,end,key,heartbeat=None):
            if heartbeat is not None: heartbeat()
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

    def test_trench_state_and_weekly_contribution_continue_without_duplicate_scoring(self):
        district = '11290'
        cell = self.cell
        area = min(1, cell['physicalInputs']['trenchDesign']['maxAreaM2'])
        self.conn.execute("""UPDATE shared_installations SET cell_id=%s,occupied_site=%s,
            model_hash=%s,facility_type='INFILTRATION_TRENCH',area_m2=%s,cost=%s WHERE id=%s""",
            (cell['id'],district+':'+cell['id'],self.native.sha256,area,area*171429,self.installation))
        self.test_real_child_replays_preserved_input_and_refuses_revised_overlap()
        self.warmup_fetch.assert_called_once()

    def test_second_installation_replays_partial_first_minute_and_preserves_prefix(self):
        self.conn.execute("""UPDATE shared_installations SET model_hash=%s,
            installed_at=installed_at+interval '17 seconds',season_ends_at=installed_at+interval '7 days',
            physics_policy='INSTALLATION_SECOND_V2',occupied_site=CAST(owner_id AS TEXT)||':'||district_id||':'||cell_id WHERE id=%s""",
            (self.native.sha256,self.installation))
        self.test_real_child_replays_preserved_input_and_refuses_revised_overlap()
        row=self.conn.execute('SELECT SUM(evaluated_seconds) seconds,SUM(evaluated_minutes) minutes FROM shared_weekly_scores WHERE installation_id=%s',(self.installation,)).fetchone()
        self.assertEqual(row['seconds'],row['minutes']*60-17)
        self.warmup_fetch.assert_called_once()

    def test_last_second_of_season_is_evaluated_and_never_republished(self):
        self.conn.execute("""UPDATE shared_installations SET model_hash=%s,
            season_ends_at=installed_at+interval '1 minute',installed_at=installed_at+interval '59 seconds',
            physics_policy='INSTALLATION_SECOND_V2',occupied_site=CAST(owner_id AS TEXT)||':'||district_id||':'||cell_id WHERE id=%s""",
            (self.native.sha256,self.installation))
        job=physics.claim(self.conn)
        self.assertIsNotNone(job)
        with tempfile.TemporaryDirectory() as root, patch.object(physics,'observed_forcing',side_effect=self.forcing):
            self.assertTrue(physics.process(self.conn,job,root))
            row=self.conn.execute('SELECT * FROM shared_physics_jobs WHERE id=%s',(job['id'],)).fetchone()
            self.assertEqual(row['state'],'SUCCEEDED',row['error_code'])
            path=Path(root)/'shared-physics'/str(job['id'])/str(job['lease_token'])
            result=json.loads((path/'result.json').read_bytes())
            self.assertEqual(result['strategy']['runoffMetrics']['observedSeconds'],1)
            self.assertEqual(datetime.fromisoformat(result['strategy']['initial']['at']),job['installation']['installed_at'])
            self.assertEqual(result['strategy']['samples'][0]['elapsedSeconds'],1)
            self.assertEqual(len(result['contribution']),1)
            score=self.conn.execute('SELECT * FROM shared_weekly_scores WHERE installation_id=%s',(self.installation,)).fetchone()
            self.assertEqual(score['evaluated_seconds'],1)
            self.assertEqual(score['rule_version'],physics.SECOND_RULE)
            self.assertAlmostEqual(float(score['score_m3']),result['contribution'][0]['cumulativeM3'],places=8)
            self.conn.execute("UPDATE shared_physics_jobs SET created_at=now()-interval '61 seconds' WHERE id=%s",(job['id'],))
            self.assertIsNone(physics.claim(self.conn))

    def test_existing_subminute_installation_keeps_full_minute_start(self):
        self.conn.execute("UPDATE shared_installations SET installed_at=installed_at+interval '17.123 seconds' WHERE id=%s",(self.installation,))
        job=physics.claim(self.conn)
        self.assertEqual(job['start'],physics.floor_minute(job['installation']['installed_at'])+timedelta(minutes=1))
        self.assertEqual(job['installation']['physics_policy'],'FULL_MINUTE_V1')
