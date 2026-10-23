"""새 관측 호출 없이 보관 입력을 재생해 주간 계산 정책을 검증·이관."""
import json
import os
from pathlib import Path
import re
import sys
import uuid
from datetime import datetime

from waterleague_sim.evaluation import score_policy
from waterleague_sim.engine.continuous import digest, ROOT
from waterleague_sim.job_runtime import read_result, run_process
from waterleague_sim.shared_physics import encode, finish, renew, verify_replayed_prefix
from waterleague_sim.weekly import aggregate, RULE, SECOND_RULE, SECOND_POLICY


def verified_inputs(directory, previous):
    directory = Path(directory)
    if directory.resolve() != directory.absolute():
        raise ValueError('LIVE_RECONCILIATION_ARCHIVE_INVALID')
    raw = (directory/'manifest.json').read_bytes()
    if digest(raw) != previous['artifact_manifest_hash']:
        raise ValueError('LIVE_RECONCILIATION_ARCHIVE_INVALID')
    manifest = json.loads(raw)
    required = {'request.json', 'model-source.json', 'forcing.json', 'result.json', 'score-policy.json'}
    if not isinstance(manifest, dict) or not required.issubset(manifest) or len(manifest) > 2048:
        raise ValueError('LIVE_RECONCILIATION_ARCHIVE_INVALID')
    for name, expected in manifest.items():
        if not isinstance(name, str):
            raise ValueError('LIVE_RECONCILIATION_ARCHIVE_INVALID')
        path = directory/name
        if (not isinstance(name, str) or Path(name).name != name or name in ('.', '..')
                or not isinstance(expected, str) or not re.fullmatch('[a-f0-9]{64}', expected)
                or path.is_symlink() or not path.is_file() or path.stat().st_size > 64*1024*1024
                or digest(path.read_bytes()) != expected):
            raise ValueError('LIVE_RECONCILIATION_ARCHIVE_INVALID')
    request_raw = (directory/'request.json').read_bytes()
    request = json.loads(request_raw)
    if (digest(request_raw) != previous['input_hash']
            or request['modelSha256'] != manifest['model-source.json']
            or request['forcingSha256'] != manifest['forcing.json']):
        raise ValueError('LIVE_RECONCILIATION_ARCHIVE_INVALID')
    if request.get('antecedentSha256') and manifest.get('antecedent.json') != request['antecedentSha256']:
        raise ValueError('LIVE_RECONCILIATION_ARCHIVE_INVALID')
    return request, manifest


def claim(conn):
    policy = digest(score_policy.verified_policy()[0])
    with conn.transaction():
        installation = conn.execute('''
            SELECT i.* FROM shared_installations i
            WHERE i.competition_id IS NULL AND i.source_retired_at IS NULL
              AND EXISTS(SELECT 1 FROM shared_weekly_scores s WHERE s.installation_id=i.id
                AND s.score_policy_sha256<>%s)
              AND NOT EXISTS(SELECT 1 FROM shared_physics_jobs j WHERE j.installation_id=i.id
                AND j.state='RUNNING')
              AND NOT EXISTS(SELECT 1 FROM shared_physics_jobs j WHERE j.installation_id=i.id
                AND j.state='FAILED' AND j.error_code LIKE 'LIVE_RECONCILIATION_%%'
                AND j.finished_at>clock_timestamp()-interval '5 minutes')
            ORDER BY i.installed_at,i.id FOR UPDATE OF i SKIP LOCKED LIMIT 1
            ''', (policy,)).fetchone()
        if installation is None:
            return None
        # 일반 워커와 같은 설치 행 잠금·RUNNING 임대로 중복 게시를 막는다.
        if conn.execute("SELECT 1 FROM shared_physics_jobs WHERE installation_id=%s AND state='RUNNING'",
                        (installation['id'],)).fetchone():
            return None
        previous = conn.execute('''SELECT * FROM shared_physics_jobs
            WHERE installation_id=%s AND state='SUCCEEDED'
            ORDER BY requested_through DESC,created_at DESC LIMIT 1''', (installation['id'],)).fetchone()
        if not previous or not previous['artifact_manifest_hash']:
            print('WEEKLY_POLICY_RECONCILIATION_ARCHIVE_UNAVAILABLE', flush=True)
            return None
        job = {'id': uuid.uuid4(), 'lease_token': uuid.uuid4(), 'installation': installation,
               'start': previous['simulation_start'], 'end': previous['requested_through'], 'previous': previous}
        conn.execute('''INSERT INTO shared_physics_jobs(id,installation_id,simulation_start,requested_through,
            state,lease_token,lease_until,created_at) VALUES(%s,%s,%s,%s,'RUNNING',%s,
            clock_timestamp()+interval '240 seconds',clock_timestamp())''',
            (job['id'], installation['id'], job['start'], job['end'], job['lease_token']))
        return job


def replay(conn, job, root):
    root = Path(root).resolve()
    previous = job['previous']
    old = root/'shared-physics'/str(previous['id'])/str(previous['lease_token'])
    path = root/'shared-physics'/str(job['id'])/str(job['lease_token'])
    path.mkdir(parents=True, exist_ok=False)
    try:
        request, manifest = verified_inputs(old, previous)
        installation = job['installation']
        rule = SECOND_RULE if installation['physics_policy'] == SECOND_POLICY else RULE
        current = score_policy.freeze('WEEKLY', rule)
        prior = score_policy.replay_context(old, request.get('scoreContext'), current)
        old_result = read_result(old/'result.json')
        previous_public = json.loads(previous['result'])
        forcing = json.loads((old/'forcing.json').read_bytes())
        if (request['installationId'] != str(installation['id'])
                or request.get('weeklyRuleVersion', RULE) != rule
                or request['siteModelHash'] != installation['model_hash']
                or old_result.get('scoreContext') != prior
                or previous_public['scoreContext'] != prior
                or datetime.fromisoformat(forcing['end']) != job['end']
                or request.get('costSnapshotRaw') != installation.get('cost_snapshot')
                or request.get('costSnapshotSha256') != installation.get('cost_snapshot_sha256')
                or request.get('publicAssetPolicy') != (json.loads(installation['admission_snapshot']) if installation.get('admission_snapshot') else None)
                or request['placement'] != {'cellId': installation['cell_id'],
                    'facilityType': installation['facility_type'], 'areaM2': float(installation['area_m2'])}
                or (rule == SECOND_RULE and datetime.fromisoformat(request['installedAt']) != installation['installed_at'])):
            raise ValueError('LIVE_RECONCILIATION_INPUT_INVALID')
        renew(conn, job)
        # 관측·모델·비용 입력은 그대로 보존하고 실행 정책만 새 검증 대상으로 바꾼다.
        for name in manifest:
            if name in ('model-source.json', 'forcing.json', 'antecedent.json') or re.fullmatch(r'[a-f0-9]{64}\.(txt|json)', name):
                raw = (old/name).read_bytes()
                if digest(raw) != manifest[name]:
                    raise ValueError('LIVE_RECONCILIATION_ARCHIVE_INVALID')
                (path/name).write_bytes(raw)
        request = request | {'scoreContext': current, 'previousScoreContext': prior,
            'weeklyCodeSha256': digest((ROOT/'simulation/waterleague_sim/weekly.py').read_bytes()),
            'reconciliation': {'mode': 'STORED_OBSERVATIONS_ONLY', 'previousJobId': str(previous['id']),
                'previousInputSha256': previous['input_hash'], 'previousManifestSha256': previous['artifact_manifest_hash']}}
        request_raw = encode(request)
        (path/'request.json').write_bytes(request_raw)
        env = {k:v for k,v in os.environ.items() if k in ('PATH','LANG','LC_ALL','LIVE_SWMM_LIBRARY','NATIVE_SPATIAL_CACHE')}
        env['PYTHONPATH'] = str(ROOT/'simulation')
        if run_process([sys.executable, '-m', 'waterleague_sim.run_live_job', str(path)],
                       env=env, timeout=90, heartbeat=lambda: renew(conn, job)) != 0:
            raise ValueError('LIVE_RECONCILIATION_ENGINE_FAILED')
        result = read_result(path/'result.json')
        if result.get('scoreContext') != current or len(result['contribution']) != len(old_result['contribution']):
            raise ValueError('LIVE_RECONCILIATION_RESULT_INVALID')
        verify_replayed_prefix(old_result, result)
        score_policy.verify(current, 'WEEKLY', rule)
        score_start = installation['installed_at'] if rule == SECOND_RULE else job['start']
        weeks = aggregate(result['contribution'], score_start, job['end'], job['end'], rule=rule)
        job['score_context'], job['previous_score_context'] = current, prior
        public = previous_public | {'scoreContext': current,
            'designContract': result['designContract'], 'lifeCycleCost': result['lifeCycleCost']}
        return finish(conn, job, public, digest(request_raw), None, weeks, digest((path/'manifest.json').read_bytes()))
    except Exception as error:
        reason = str(error)
        if not re.fullmatch('LIVE_[A-Z_]{1,48}', reason):
            reason = 'LIVE_RECONCILIATION_FAILED'
        print('WEEKLY_POLICY_RECONCILIATION_REJECTED', str(job['id']), reason, flush=True)
        finish(conn, job, None, None, 'LIVE_RECONCILIATION_FAILED')
        return False


def main(limit=256):
    import psycopg
    from psycopg.rows import dict_row
    from waterleague_sim.runtime import database_url
    os.umask(0o077)
    passed = failed = 0
    with psycopg.connect(database_url(), autocommit=True, row_factory=dict_row) as conn:
        for _ in range(limit):
            job = claim(conn)
            if job is None:
                break
            if replay(conn, job, os.environ['ARTIFACTS_PATH']):
                passed += 1
            else:
                failed += 1
            print('WEEKLY_POLICY_RECONCILIATION', json.dumps({'passed':passed,'failed':failed}), flush=True)
    return passed, failed


if __name__ == '__main__':
    main()
