"""과거 강우 연구 계산 프로세스의 제한 실행·임대 결과 게시."""
import json
import os
import signal
import subprocess
import sys
import time
from decimal import Decimal
from pathlib import Path
from .engine.continuous import ROOT
from .queue import finish


def process(conn, job, artifacts):
    path = Path(artifacts)/'historical'/str(job['id'])/str(job['lease_token'])
    path.mkdir(parents=True,exist_ok=False)
    request = {'modelHash': job['model_hash'], 'placements': job['placements'], 'inputHash': job['input_hash']}
    (path/'request.json').write_text(json.dumps(request,ensure_ascii=False)+'\n')
    env = {k:v for k,v in os.environ.items() if k in ('PATH','LANG','LC_ALL','LIVE_SWMM_LIBRARY','NATIVE_SPATIAL_CACHE')}
    env['PYTHONPATH'] = str(ROOT/'simulation')
    result, error = None, 'HISTORICAL_ENGINE_FAILED'
    try:
        submission = json.loads(job['placements'])[0].get('submissionPolicy') == 'FULL_EVENT_INDEPENDENT_SURFACES_V1'
        module = 'run_historical_submission' if submission else 'run_historical_job'
        child = subprocess.Popen([sys.executable,'-m','waterleague_sim.'+module,str(path)],
            env=env,start_new_session=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        deadline = time.monotonic() + (600 if submission else 90)
        while True:
            try:
                code = child.wait(timeout=min(30, max(.01,deadline-time.monotonic())))
                break
            except subprocess.TimeoutExpired:
                if time.monotonic() >= deadline:
                    raise
                with conn.transaction():
                    renewed = conn.execute("UPDATE historical_experiments SET lease_until=clock_timestamp()+interval '180 seconds'"
                        " WHERE id=%s AND state='RUNNING' AND lease_token=%s AND lease_until>clock_timestamp()",
                        (job['id'],job['lease_token'])).rowcount
                if renewed != 1:
                    os.killpg(child.pid,signal.SIGKILL); child.wait()
                    return False
        if code == 0:
            result = json.loads((path/'result.json').read_text())
            error = None
    except subprocess.TimeoutExpired:
        os.killpg(child.pid,signal.SIGKILL)
        child.wait()
        error = 'HISTORICAL_ENGINE_TIMEOUT'
    except (OSError,ValueError):
        error = 'HISTORICAL_RESULT_INVALID'
    with conn.transaction():
        published = finish(conn,job,'SUCCEEDED' if result is not None else 'FAILED',result,error)
        if published and result is not None and submission:
            conn.execute('UPDATE historical_submissions SET difference_m3=%s WHERE job_id=%s AND rules_hash=%s',
                (Decimal(str(result['differenceM3'])),job['id'],result['rulesHash']))
    return published
