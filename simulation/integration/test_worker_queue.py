"""별도 임시 PostgreSQL에서 두 큐의 경합·lease·실제 SWMM 실행 검증."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import threading
import unittest
import uuid
from unittest.mock import patch

import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row

from waterleague_sim import queue, worker
from waterleague_sim.engine.swmm import library_path


class WorkerQueueTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dsn = os.environ.get('WL_WORKER_TEST_DSN', '')
        config = conninfo_to_dict(cls.dsn)
        # 운영 DB·다른 시험 DB의 자료 삭제를 막기 위해 전용 임시 이름만 허용한다.
        if config.get('host') not in {'127.0.0.1', 'localhost', '::1'} or not re.fullmatch(
                r'waterleague_queue_test_[a-f0-9]{32}', config.get('dbname', '')):
            raise RuntimeError('전용 로컬 임시 DB 필요')
        if config.get('dbname') == conninfo_to_dict(os.environ.get('DATABASE_URL', '')).get('dbname'):
            raise RuntimeError('원본 DB 사용 거부')
        cls.source = (worker.ROOT / 'data/models/seongsu-lab.json').read_bytes()
        cls.model_hash = hashlib.sha256(cls.source).hexdigest()
        cls.placements = '[{"cellId":"G1","facilityType":"RAIN_GARDEN","areaM2":40}]'
        cls.input_hash = hashlib.sha256((cls.model_hash + '\n' + cls.placements).encode()).hexdigest()

    def connection(self):
        return psycopg.connect(self.dsn, autocommit=True, row_factory=dict_row)

    def setUp(self):
        self.conn = self.connection()
        self.addCleanup(self.conn.close)
        self.conn.execute('TRUNCATE accounts,organizations CASCADE')
        self.owner, self.org, self.version, self.group = [uuid.uuid4() for _ in range(4)]
        self.conn.execute('INSERT INTO organizations(id,name,approved) VALUES(%s,%s,true)',
                          (self.org, '격리된 큐 시험 기관'))
        self.conn.execute("""INSERT INTO accounts(id,username,display_name,password_hash,role,
            member_type,approval_status,enabled,created_at)
            VALUES(%s,'queue_test','큐 시험','NOT_A_LOGIN','MEMBER','PLAYER','APPROVED',true,now())""",
            (self.owner,))
        strategy = uuid.uuid4()
        self.conn.execute("INSERT INTO strategies(id,owner_id,title,created_at) VALUES(%s,%s,'큐 시험',now())",
                          (strategy, self.owner))
        self.conn.execute("""INSERT INTO strategy_versions(id,strategy_id,revision,model_hash,
            input_hash,placements,events,design_note,cost,currency,created_at)
            VALUES(%s,%s,1,%s,%s,%s,'[]','시험용',22400000,'KRW',now())""",
            (self.version, strategy, self.model_hash, self.input_hash, self.placements))
        self.conn.execute("""INSERT INTO research_searches(id,organization_id,requested_by,request_key,
            request_hash,model_hash,budget_krw,seed,top_k,candidates_per_arm,provenance,provenance_hash,created_at)
            VALUES(%s,%s,%s,%s,%s,%s,100000000,0,2,4,'{}',%s,now())""",
            (self.group, self.org, self.owner, uuid.uuid4(), 'b' * 64, self.model_hash, 'c' * 64))
        self.temp = tempfile.TemporaryDirectory(prefix='waterleague-queue-artifacts-')
        self.addCleanup(self.temp.cleanup)
        self.artifacts = Path(self.temp.name) / 'runs'
        self.next_ordinal = 0

    def add(self, kind, age=0, same_input=False):
        job_id = uuid.uuid4()
        created = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=age)
        if kind == 'PERSONAL':
            self.conn.execute("""INSERT INTO simulation_jobs(id,version_id,owner_id,request_key,
                state,model_hash,input_hash,created_at) VALUES(%s,%s,%s,%s,'QUEUED',%s,%s,%s)""",
                (job_id, self.version, self.owner, uuid.uuid4(), self.model_hash, self.input_hash, created))
        else:
            self.next_ordinal += 1
            ordinal = (self.next_ordinal - 1) % 4 + 1
            arm = 'PATTERN' if self.next_ordinal <= 4 else 'UNIFORM'
            input_hash = self.input_hash if same_input else hashlib.sha256(str(job_id).encode()).hexdigest()
            self.conn.execute("""INSERT INTO research_candidates(id,search_id,arm,ordinal,placements,
                model_hash,input_hash,cost,state,created_at)
                VALUES(%s,%s,%s,%s,%s,%s,%s,22400000,'QUEUED',%s)""",
                (job_id, self.group, arm, ordinal, self.placements, self.model_hash, input_hash, created))
        return job_id

    def row(self, kind, job_id):
        return self.conn.execute(psycopg.sql.SQL('SELECT * FROM {} WHERE id=%s').format(queue.table(kind)),
                                 (job_id,)).fetchone()

    def expire(self, job):
        self.conn.execute(psycopg.sql.SQL("UPDATE {} SET lease_until=now()-interval '1 second' WHERE id=%s")
                          .format(queue.table(job['queue_kind'])), (job['id'],))

    def test_oldest_eligible_job_across_both_queues_and_running_exclusion(self):
        ids = [self.add('PERSONAL', 2), self.add('RESEARCH_CANDIDATE', 1),
               self.add('RESEARCH_CANDIDATE', 3), self.add('PERSONAL', 0)]
        claimed = [queue.claim(self.conn) for _ in ids]
        self.assertEqual([j['id'] for j in claimed], [ids[3], ids[1], ids[0], ids[2]])
        self.assertIsNone(queue.claim(self.conn))
        for job in claimed:
            row = self.row(job['queue_kind'], job['id'])
            self.assertEqual(row['state'], 'RUNNING')
            self.assertEqual(row['attempts'], 1)
            self.assertGreater(row['lease_until'], datetime.now(timezone.utc))

    def test_concurrent_workers_claim_each_job_once(self):
        ids = {self.add(kind, age) for age, kind in enumerate(['PERSONAL', 'RESEARCH_CANDIDATE'] * 4)}
        barrier = threading.Barrier(8)

        def claim():
            with self.connection() as conn:
                barrier.wait(timeout=10)
                return queue.claim(conn)['id']

        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = [pool.submit(claim) for _ in ids]
            result = [future.result(timeout=15) for future in futures]
        self.assertEqual(set(result), ids)
        self.assertEqual(len(result), len(set(result)))

    def test_skips_locked_job_and_obeys_common_admission_lock(self):
        oldest = self.add('RESEARCH_CANDIDATE', 0)
        next_id = self.add('PERSONAL', 1)
        with self.connection() as blocker, ThreadPoolExecutor(max_workers=1) as pool:
            with blocker.transaction():
                blocker.execute('SELECT id FROM research_candidates WHERE id=%s FOR UPDATE', (oldest,))
                future = pool.submit(self.claim_with_connection)
                self.assertEqual(future.result(timeout=3)['id'], next_id)
            started = threading.Event()
            with blocker.transaction():
                blocker.execute('SELECT id FROM queue_admission WHERE id=1 FOR UPDATE')
                future = pool.submit(self.claim_with_connection, started)
                self.assertTrue(started.wait(timeout=3))
                with self.assertRaises(TimeoutError):
                    future.result(timeout=0.2)
            self.assertEqual(future.result(timeout=3)['id'], oldest)

    def claim_with_connection(self, started=None):
        with self.connection() as conn:
            if started:
                started.set()
            return queue.claim(conn)

    def test_expired_and_replaced_leases_cannot_publish_and_three_attempts_are_final(self):
        for kind in queue.TABLES:
            with self.subTest(kind=kind):
                job_id = self.add(kind)
                first = queue.claim(self.conn)
                self.expire(first)
                self.assertFalse(queue.finish(self.conn, first, 'SUCCEEDED', {'stale': True}, None))
                second = queue.claim(self.conn)
                self.assertNotEqual(second['lease_token'], first['lease_token'])
                self.assertEqual(second['attempts'], 2)
                self.assertFalse(queue.finish(self.conn, first, 'FAILED', None, 'STALE'))
                self.assertEqual(self.row(kind, job_id)['state'], 'RUNNING')
                self.expire(second)
                third = queue.claim(self.conn)
                self.assertEqual(third['attempts'], 3)
                self.expire(third)
                self.assertIsNone(queue.claim(self.conn))
                row = self.row(kind, job_id)
                self.assertEqual((row['state'], row['error_code']), ('FAILED', 'WORKER_RETRY_EXHAUSTED'))
                self.assertIsNone(row['lease_until'])
                self.assertFalse(queue.finish(self.conn, third, 'SUCCEEDED', {}, None))

    def test_rejects_unknown_queue_and_wrong_lease_without_changing_record(self):
        job_id = self.add('RESEARCH_CANDIDATE')
        job = queue.claim(self.conn)
        with self.assertRaises(ValueError):
            queue.finish(self.conn, job | {'queue_kind': 'simulation_jobs;DELETE FROM accounts'}, 'FAILED', None, 'NO')
        self.assertFalse(queue.finish(self.conn, job | {'lease_token': uuid.uuid4()}, 'FAILED', None, 'NO'))
        self.assertEqual(self.row('RESEARCH_CANDIDATE', job_id)['state'], 'RUNNING')
        self.assertEqual(self.conn.execute('SELECT COUNT(*) n FROM accounts').fetchone()['n'], 1)

    def test_bad_hash_and_invalid_json_are_rejected_before_engine(self):
        job_id = self.add('RESEARCH_CANDIDATE')
        with patch.object(worker, 'ARTIFACTS', self.artifacts), patch.object(worker.subprocess, 'Popen') as child:
            self.assertTrue(worker.process(self.conn, queue.claim(self.conn)))
            self.assertEqual(self.row('RESEARCH_CANDIDATE', job_id)['error_code'], 'INPUT_HASH_MISMATCH')
            invalid = self.add('RESEARCH_CANDIDATE')
            raw = 'INVALID_JSON'
            self.conn.execute('UPDATE research_candidates SET placements=%s,input_hash=%s WHERE id=%s',
                              (raw, hashlib.sha256((self.model_hash + '\n' + raw).encode()).hexdigest(), invalid))
            self.assertTrue(worker.process(self.conn, queue.claim(self.conn)))
            self.assertEqual(self.row('RESEARCH_CANDIDATE', invalid)['error_code'], 'INPUT_INVALID')
            child.assert_not_called()

    def test_real_engine_preserves_queue_ownership_and_separate_artifacts_with_cache_reuse(self):
        self.assertTrue(library_path().is_file(), '실제 SWMM 엔진 빌드 필요')
        personal = self.add('PERSONAL', 0)
        candidate = self.add('RESEARCH_CANDIDATE', 1, same_input=True)
        originals = self.conn.execute('SELECT * FROM strategy_versions').fetchall()
        with patch.object(worker, 'ARTIFACTS', self.artifacts), patch.dict(os.environ, {
            'SWMM_LIBRARY': str(library_path()), 'SIMULATION_CACHE_PATH': str(Path(self.temp.name) / 'cache'),
            'SIMULATION_CACHE_ENABLED': 'true',
        }):
            for _ in range(2):
                self.assertTrue(worker.process(self.conn, queue.claim(self.conn)))
        self.assertEqual(self.conn.execute('SELECT * FROM strategy_versions').fetchall(), originals)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) n FROM simulation_jobs').fetchone()['n'], 1)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) n FROM submissions').fetchone()['n'], 0)
        results = []
        for kind, job_id in [('PERSONAL', personal), ('RESEARCH_CANDIDATE', candidate)]:
            row = self.row(kind, job_id)
            self.assertEqual(row['state'], 'SUCCEEDED')
            result = json.loads(row['result'])
            prefix = self.artifacts if kind == 'PERSONAL' else self.artifacts / 'research-candidates'
            directory = prefix / str(job_id) / result['artifactToken']
            manifest = json.loads((directory / 'manifest.json').read_text())
            self.assertEqual(len(manifest), 18)
            for name, expected in manifest.items():
                self.assertEqual(hashlib.sha256((directory / name).read_bytes()).hexdigest(), expected)
            self.assertEqual(result['modelHash'], self.model_hash)
            self.assertEqual(result['inputHash'], self.input_hash)
            self.assertEqual(result['validationLevel'], 'EXPLORATORY')
            self.assertFalse(result['official'])
            results.append(result)
        self.assertEqual([r['execution']['mode'] for r in results], ['COMPUTED', 'REUSED'])
        for name in ['baseline', 'strategy', 'score', 'sensitivity', 'engine']:
            self.assertEqual(results[0][name], results[1][name])
        self.assertFalse((self.artifacts / str(candidate)).exists())


if __name__ == '__main__':
    unittest.main()
