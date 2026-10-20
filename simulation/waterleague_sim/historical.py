"""과거 강우 연구 계산 프로세스의 제한 실행·임대 결과 게시."""
import json
import os
import subprocess
import sys
from decimal import Decimal
from pathlib import Path
from .engine.continuous import ROOT
from .queue import finish, renew
from .evaluation import score_policy
from .job_runtime import run_process, read_result


def process(conn, job, artifacts):
    path = Path(artifacts)/'historical'/str(job['id'])/str(job['lease_token'])
    path.mkdir(parents=True,exist_ok=False)
    request = {'modelHash': job['model_hash'], 'placements': job['placements'], 'inputHash': job['input_hash']}
    (path/'request.json').write_text(json.dumps(request,ensure_ascii=False)+'\n')
    env = {k:v for k,v in os.environ.items() if k in ('PATH','LANG','LC_ALL','LIVE_SWMM_LIBRARY','NATIVE_SPATIAL_CACHE')}
    env['PYTHONPATH'] = str(ROOT/'simulation')
    result, error = None, 'HISTORICAL_ENGINE_FAILED'
    submission = False
    try:
        submission = json.loads(job['placements'])[0].get('submissionPolicy') == 'FULL_EVENT_INDEPENDENT_SURFACES_V1'
        if submission:
            head = json.loads(job['placements'])[0]
            rules = json.loads(head['submissionRulesRaw'])
            raw, _ = score_policy.verified_policy()
            if rules.get('scorePolicy', {}).get('sha256') != score_policy.digest(raw):
                raise ValueError('LIVE_SCORE_POLICY_INVALID')
            request['scoreContext'] = score_policy.freeze('SUBMISSION', head['submissionRulesHash'])
            (path/'request.json').write_text(json.dumps(request, ensure_ascii=False)+'\n')
        module = 'run_historical_submission' if submission else 'run_historical_job'
        code = run_process([sys.executable,'-m','waterleague_sim.'+module,str(path)],
                           env=env, timeout=600 if submission else 90, heartbeat=lambda: renew(conn, job))
        if code == 0:
            result = read_result(path/'result.json')
            if submission:
                context = score_policy.verify(result.get('scoreContext'), 'SUBMISSION', head['submissionRulesHash'])
                if (context != request['scoreContext'] or result.get('rulesHash') != head['submissionRulesHash']
                        or result['rankingScoreM3Exact'] != format(score_policy.quantize(result['differenceM3'], 18), 'f')):
                    raise ValueError('LIVE_SCORE_CONTEXT_INVALID')
            error = None
    except subprocess.TimeoutExpired:
        error = 'HISTORICAL_ENGINE_TIMEOUT'
    except (OSError,ValueError,KeyError,IndexError,TypeError):
        result, error = None, 'HISTORICAL_RESULT_INVALID'
    with conn.transaction():
        published = finish(conn,job,'SUCCEEDED' if result is not None else 'FAILED',result,error)
        if published and result is not None and submission:
            updated = conn.execute('UPDATE historical_submissions SET difference_m3=%s,score_policy_sha256=%s,comparison_group_hash=%s '
                'WHERE job_id=%s AND rules_hash=%s',
                (Decimal(result['rankingScoreM3Exact']),context['policySha256'],context['sha256'],job['id'],result['rulesHash'])).rowcount
            if updated != 1:
                raise ValueError('HISTORICAL_SUBMISSION_RULES_INVALID')
    return published
