"""명시한 TEST 대회 제출만 개최 당시 계산 버전으로 처리하는 유한 워커."""
import json
import os
from pathlib import Path
import sys
import time
import uuid

if os.environ.get('WATERLEAGUE_TEST_COMPETITION') != 'TEST_COMPETITIONS_20261022':
    raise SystemExit('TEST_COMPETITION_REQUIRED')

from psycopg.rows import dict_row
import psycopg
from waterleague_sim.evaluation.score_policy import digest, verified_policy
from waterleague_sim.historical import process
from waterleague_sim.runtime import database_url
from waterleague_sim.spatial.play_bundle import open_catalog

directory = Path(sys.argv[1])
plan = json.loads((directory/'plan.json').read_text())
progress = json.loads((directory/'progress.json').read_text())
identifiers = [uuid.UUID(p['jobId']) for p in progress['players'].values()]
if len(identifiers) != 10 or len(set(identifiers)) != 10:
    raise SystemExit('TEST_COMPETITION_JOBS_INVALID')
if plan['runtimePolicySha256'] != digest(verified_policy()[0]):
    raise SystemExit('TEST_COMPETITION_POLICY_INVALID')
owners = {uuid.UUID(p['ownerId']) for p in plan['players']}
if len(owners) != 10 or any(not p['username'].startswith('TEST_20261022_') for p in plan['players']):
    raise SystemExit('TEST_COMPETITION_OWNERS_INVALID')

open_catalog()
deadline = time.monotonic()+3600
with psycopg.connect(database_url(), autocommit=True, row_factory=dict_row) as conn:
    previous = None
    while time.monotonic() < deadline:
        rows = conn.execute("""
            SELECT j.id,j.owner_id,j.state,j.error_code FROM historical_experiments j
            JOIN game_competition_participants p ON p.owner_id=j.owner_id AND p.competition_id=%s
            WHERE j.id=ANY(%s)
            """, (uuid.UUID(plan['competitionId']), identifiers)).fetchall()
        if len(rows) != 10 or {r['owner_id'] for r in rows} != owners:
            raise SystemExit('TEST_COMPETITION_OWNERS_INVALID')
        states = {}
        for row in rows:
            states[row['state']] = states.get(row['state'], 0)+1
        if states != previous:
            print('TEST_COMPETITION_QUEUE', json.dumps(states), flush=True)
            previous = states
        failures = [r['error_code'] for r in rows if r['state'] in ('FAILED', 'REJECTED')]
        if failures:
            print('TEST_COMPETITION_FAILURES', json.dumps(failures), flush=True)
            raise SystemExit(1)
        if states.get('SUCCEEDED') == 10:
            print('TEST_COMPETITION_COMPLETE', flush=True)
            break
        # 일반 큐의 입장 잠금·임대·fencing을 유지하며 지정 작업에만 임대를 발급한다.
        with conn.transaction():
            if not conn.execute('SELECT id FROM queue_admission WHERE id=1 FOR UPDATE').fetchone():
                raise SystemExit('TEST_COMPETITION_ADMISSION_MISSING')
            job = conn.execute("""
                SELECT * FROM historical_experiments
                WHERE id=ANY(%s) AND attempts<3
                  AND (state='QUEUED' OR (state='RUNNING' AND lease_until<=clock_timestamp()))
                ORDER BY created_at,id FOR UPDATE SKIP LOCKED LIMIT 1
                """, (identifiers,)).fetchone()
            if job:
                token = uuid.uuid4()
                conn.execute("""
                    UPDATE historical_experiments SET state='RUNNING',attempts=attempts+1,
                        lease_token=%s,lease_until=clock_timestamp()+interval '180 seconds',
                        finished_at=NULL,error_code=NULL,result=NULL WHERE id=%s
                    """, (token, job['id']))
                job = job | {'lease_token': token, 'attempts': job['attempts']+1, 'queue_kind': 'HISTORICAL'}
        if job:
            process(conn, job, Path(os.environ['ARTIFACTS_PATH']))
        else:
            time.sleep(2)
    else:
        raise SystemExit('TEST_COMPETITION_DEADLINE')
