"""요청한 TEST 실행이 끝날 때까지 기존 임대 큐 처리기를 실행하는 일회성 워커."""
import json
import os
from pathlib import Path
import sys
import time
import uuid

if os.environ.get('WATERLEAGUE_TEST_BATCH') != 'TEST_20261022':
    raise SystemExit('TEST_BATCH_REQUIRED')

inputs = json.loads(Path(sys.argv[1]).read_text())
identifiers = [uuid.UUID(value) for value in inputs['jobIds']]
if len(identifiers) != 20 or len(set(identifiers)) != 20:
    raise SystemExit('TEST_JOB_SET_INVALID')

os.environ['KMA_API_KEY'] = Path('/run/secrets/kma-api-key').read_text()
from waterleague_sim.worker import process
from waterleague_sim.queue import claim
from waterleague_sim.runtime import database_url
from waterleague_sim.spatial.play_bundle import open_catalog
import psycopg
from psycopg.rows import dict_row

open_catalog()
deadline = time.monotonic() + 3600
with psycopg.connect(database_url(), autocommit=True, row_factory=dict_row) as connection:
    previous = None
    while time.monotonic() < deadline:
        rows = connection.execute(
            'SELECT id,state,error_code FROM historical_experiments WHERE id=ANY(%s)',
            (identifiers,),
        ).fetchall()
        if len(rows) != 20:
            raise SystemExit('TEST_JOB_SET_MISSING')
        states = {}
        for row in rows:
            states[row['state']] = states.get(row['state'], 0) + 1
        if states != previous:
            print('TEST_QUEUE_STATES', json.dumps(states), flush=True)
            previous = states
        failed = [row['error_code'] for row in rows if row['state'] in ('FAILED', 'REJECTED')]
        if failed:
            print('TEST_QUEUE_FAILED', json.dumps(failed), flush=True)
            raise SystemExit(1)
        if states.get('SUCCEEDED') == 20:
            print('TEST_QUEUE_COMPLETED', flush=True)
            break
        # 기존 claim/process의 잠금·임대·해시 검증을 사용해 다른 워커와 중복 계산하지 않는다.
        job = claim(connection)
        if job:
            process(connection, job)
        else:
            time.sleep(2)
    else:
        raise SystemExit('TEST_QUEUE_DEADLINE')
