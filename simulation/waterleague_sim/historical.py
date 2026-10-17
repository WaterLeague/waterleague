"""과거 강우 연구 계산 프로세스의 제한 실행·임대 결과 게시."""
import json
import os
import signal
import subprocess
import sys
from pathlib import Path
from .engine.continuous import ROOT
from .queue import finish


def process(conn, job, artifacts):
    path = Path(artifacts)/'historical'/str(job['id'])/str(job['lease_token'])
    path.mkdir(parents=True,exist_ok=False)
    request = {'modelHash': job['model_hash'], 'placements': job['placements'], 'inputHash': job['input_hash']}
    (path/'request.json').write_text(json.dumps(request,ensure_ascii=False)+'\n')
    env = {k:v for k,v in os.environ.items() if k in ('PATH','LANG','LC_ALL','LIVE_SWMM_LIBRARY')}
    env['PYTHONPATH'] = str(ROOT/'simulation')
    result, error = None, 'HISTORICAL_ENGINE_FAILED'
    try:
        child = subprocess.Popen([sys.executable,'-m','waterleague_sim.run_historical_job',str(path)],
            env=env,start_new_session=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        if child.wait(timeout=90) == 0:
            result = json.loads((path/'result.json').read_text())
            error = None
    except subprocess.TimeoutExpired:
        os.killpg(child.pid,signal.SIGKILL)
        child.wait()
        error = 'HISTORICAL_ENGINE_TIMEOUT'
    except (OSError,ValueError):
        error = 'HISTORICAL_RESULT_INVALID'
    return finish(conn,job,'SUCCEEDED' if result is not None else 'FAILED',result,error)
