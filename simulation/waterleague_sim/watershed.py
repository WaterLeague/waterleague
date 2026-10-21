"""공개 관망 회원 계산의 자원 제한·lease 결과 게시."""
import json
import os
from pathlib import Path
import subprocess
import sys
from .engine.swmm import ROOT
from .queue import finish, renew
from .job_runtime import run_process, read_result


def process(conn, job, artifacts):
    directory=Path(artifacts)/'watersheds'/str(job['id'])/str(job['lease_token'])
    directory.mkdir(parents=True, exist_ok=False)
    request={'modelHash':job['model_hash'], 'inputHash':job['input_hash'], 'placements':job['placements']}
    (directory/'request.json').write_text(json.dumps(request, ensure_ascii=False)+'\n')
    env={key:value for key,value in os.environ.items()
         if key in ('PATH','LANG','LC_ALL','SIMULATION_CACHE_ENABLED','WATERSHED_CACHE_PATH')}
    env['PYTHONPATH']=str(ROOT/'simulation')
    result,error=None,'WATERSHED_ENGINE_FAILED'
    try:
        design = json.loads(job['placements'])
        timeout = 150
        if 'surfaceConnection' in design:
            from .watershed_surface import verify
            verify(design)
            timeout = 7200
        if run_process([sys.executable,'-m','waterleague_sim.run_watershed_job',str(directory)],
                       env=env, timeout=timeout, heartbeat=lambda: renew(conn,job))==0:
            result=read_result(directory/'result.json')
            if result.get('inputHash') != job['input_hash'] or result.get('catalogHash') != job['model_hash']:
                raise ValueError('WATERSHED_RESULT_INVALID')
            error=None
    except subprocess.TimeoutExpired:
        error='WATERSHED_ENGINE_TIMEOUT'
    except (OSError,ValueError):
        result=None;error='WATERSHED_RESULT_INVALID'
    return finish(conn,job,'SUCCEEDED' if result is not None else 'FAILED',result,error)
