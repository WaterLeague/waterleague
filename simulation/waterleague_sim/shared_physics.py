"""공동 설치 관측 구간의 원자적 임대·연속 재생·상태 게시."""
import json
import os
import re
import subprocess
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from .engine.continuous import ROOT, digest, engine_identity
from .ingestion.live import observed_forcing
from .ingestion.evaporation import observed_evaporation, append_evaporation, reusable_observation_hour
from .installation_model import resolve, with_observed_forcing
from .ingestion import source_archive
from .weekly import aggregate as weekly_aggregate, publish as publish_weekly, RULE, SECOND_RULE, SECOND_POLICY
from .evaluation import score_policy
from .job_runtime import run_process, read_result


def encode(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)+'\n').encode()


def floor_minute(at):
    return at.replace(second=0, microsecond=0)


def claim(conn):
    with conn.transaction():
        conn.execute("""UPDATE shared_physics_jobs SET state='FAILED',error_code='LIVE_LEASE_EXPIRED',
            finished_at=clock_timestamp(),lease_until=NULL WHERE state='RUNNING' AND lease_until<=clock_timestamp()""")
        installation = conn.execute("""
            SELECT i.* FROM shared_installations i
            WHERE i.source_retired_at IS NULL AND date_trunc('minute',LEAST(COALESCE(i.removed_at,i.season_ends_at,clock_timestamp()),clock_timestamp()-interval '2 minutes'))
                > date_trunc('minute',i.installed_at)+CASE WHEN i.installed_at=date_trunc('minute',i.installed_at)
                    OR i.physics_policy='INSTALLATION_SECOND_V2' THEN interval '0 minutes' ELSE interval '1 minute' END
              AND NOT EXISTS(SELECT 1 FROM shared_physics_jobs j WHERE j.installation_id=i.id AND j.state='RUNNING')
              AND NOT EXISTS(SELECT 1 FROM shared_physics_jobs j WHERE j.installation_id=i.id AND j.created_at>clock_timestamp()-interval '60 seconds')
              AND NOT EXISTS(SELECT 1 FROM shared_physics_jobs j WHERE j.installation_id=i.id AND j.state='FAILED'
                AND COALESCE(j.finished_at,j.created_at)>clock_timestamp()-interval '5 minutes')
              AND NOT EXISTS(SELECT 1 FROM shared_physics_jobs j WHERE j.installation_id=i.id AND j.state='SUCCEEDED'
                AND j.requested_through>=date_trunc('minute',LEAST(COALESCE(i.removed_at,i.season_ends_at,clock_timestamp()),clock_timestamp()-interval '2 minutes')))
            ORDER BY (SELECT max(j.created_at) FROM shared_physics_jobs j WHERE j.installation_id=i.id) NULLS FIRST,i.installed_at,i.id
            FOR UPDATE OF i SKIP LOCKED LIMIT 1
            """).fetchone()
        if not installation:
            return None
        # 설치 행 잠금 뒤 새 스냅샷으로 중복 임대 여부를 다시 확인한다.
        if conn.execute("""SELECT 1 FROM shared_physics_jobs WHERE installation_id=%s AND
                        (state='RUNNING' OR created_at>clock_timestamp()-interval '60 seconds'
                         OR (state='FAILED' AND COALESCE(finished_at,created_at)>clock_timestamp()-interval '5 minutes'))""",
                        (installation['id'],)).fetchone():
            return None
        previous = conn.execute("""SELECT * FROM shared_physics_jobs WHERE installation_id=%s AND state='SUCCEEDED'
            ORDER BY requested_through DESC,created_at DESC LIMIT 1""", (installation['id'],)).fetchone()
        start = floor_minute(installation['installed_at'])
        if installation['physics_policy'] != SECOND_POLICY and start < installation['installed_at']:
            start += timedelta(minutes=1)
        covered = previous['requested_through'] if previous else start
        now = conn.execute('SELECT clock_timestamp() AS now').fetchone()['now']
        end = min(floor_minute(now)-timedelta(minutes=2), covered+timedelta(hours=23))
        if stops := installation['removed_at'] or installation.get('season_ends_at'):
            end = min(end, floor_minute(stops))
        if end <= covered:
            return None
        job = {'id': uuid.uuid4(), 'lease_token': uuid.uuid4(), 'installation': installation,
               'start': start, 'end': end, 'previous': previous}
        conn.execute("""INSERT INTO shared_physics_jobs(id,installation_id,simulation_start,requested_through,
            state,lease_token,lease_until,created_at) VALUES(%s,%s,%s,%s,'RUNNING',%s,clock_timestamp()+interval '240 seconds',clock_timestamp())""",
            (job['id'], installation['id'], start, end, job['lease_token']))
        return job


def renew(conn, job):
    # 만료된 임대의 부활 없이 실제 수집 진행마다 소유 토큰을 확인한다.
    with conn.transaction():
        conn.execute('SELECT id FROM shared_physics_jobs WHERE id=%s FOR UPDATE', (job['id'],)).fetchone()
        changed = conn.execute("""UPDATE shared_physics_jobs SET lease_until=clock_timestamp()+interval '240 seconds'
            WHERE id=%s AND lease_token=%s AND state='RUNNING' AND lease_until>clock_timestamp()""",
            (job['id'],job['lease_token'])).rowcount
    if changed != 1:
        raise ValueError('LIVE_LEASE_LOST')


def finish(conn, job, result, input_hash, error, weeks=None, manifest_hash=None):
    with conn.transaction():
        conn.execute('SELECT id FROM shared_physics_jobs WHERE id=%s FOR UPDATE', (job['id'],)).fetchone()
        saved = conn.execute("""UPDATE shared_physics_jobs SET state=%s,result=%s,input_hash=%s,error_code=%s,
            finished_at=clock_timestamp(),lease_until=NULL,artifact_manifest_hash=%s WHERE id=%s AND state='RUNNING'
            AND lease_token=%s AND lease_until>clock_timestamp()""",
            ('SUCCEEDED' if result is not None else 'FAILED', json.dumps(result, ensure_ascii=False, allow_nan=False) if result else None,
             input_hash, error, manifest_hash, job['id'], job['lease_token'])).rowcount == 1
        if saved and result is not None:
            if weeks is None:
                raise ValueError('LIVE_WEEKLY_INPUT_MISSING')
            publish_weekly(conn, job, weeks)
            if job.get("competition_frames") is not None:
                from .competition_scores import publish as publish_competitions
                publish_competitions(conn, job, job["competition_frames"])
        return saved


def process(conn, job, root):
    root = Path(root).resolve()
    path = Path(root)/'shared-physics'/str(job['id'])/str(job['lease_token'])
    path.mkdir(parents=True, exist_ok=False)
    try:
        model, station, station_name = resolve(job['installation'])
        timed = job['installation'].get('physics_policy') == SECOND_POLICY
        score_start = job['installation']['installed_at'] if timed else job['start']
        rule = SECOND_RULE if timed else RULE
        comparison_context = score_policy.freeze('WEEKLY', rule)
        job['score_context'] = comparison_context
        engine = engine_identity()
        observations, source_hashes, previous_ref, previous_result = [], [], None, None
        previous_evaporation = None
        previous_directory = None
        previous_manifest = {}
        antecedent, antecedent_sources = None, []
        covered = job['start']
        if previous := job['previous']:
            old = Path(root)/'shared-physics'/str(previous['id'])/str(previous['lease_token'])
            previous_directory = old
            raw = (old/'forcing.json').read_bytes()
            req_raw = (old/'request.json').read_bytes()
            req = json.loads(req_raw)
            forcing = json.loads(raw)
            if (digest(req_raw) != previous['input_hash'] or digest(raw) != req['forcingSha256']
                    or req.get('scoreContext') != comparison_context
                    or {k:v for k,v in req['engine'].items() if k!='adapterSha256'} != {k:v for k,v in engine.items() if k!='adapterSha256'}
                    or req.get('weeklyRuleVersion', RULE) != rule
                    or (timed and datetime.fromisoformat(req.get('installedAt', '')) != score_start)
                    or req['installationId'] != str(job['installation']['id'])
                    or forcing['stationId'] != station or datetime.fromisoformat(forcing['start']) != job['start']
                    or datetime.fromisoformat(forcing['end']) != previous['requested_through']):
                raise ValueError('LIVE_PREVIOUS_INPUT_INVALID')
            result_raw = (old/'result.json').read_bytes()
            if previous.get('artifact_manifest_hash'):
                manifest_raw = (old/'manifest.json').read_bytes()
                manifest = json.loads(manifest_raw)
                previous_manifest = manifest
                if (digest(manifest_raw) != previous['artifact_manifest_hash']
                        or manifest.get('result.json') != digest(result_raw)):
                    raise ValueError('LIVE_PREVIOUS_RESULT_INVALID')
            previous_result = json.loads(result_raw)
            observations, source_hashes = forcing['observations'], forcing['sourceHashes']
            previous_evaporation = forcing.get('evaporation')
            covered = previous['requested_through']
            previous_ref = {'jobId': str(previous['id']), 'leaseToken': str(previous['lease_token']),
                            'requestSha256': digest(req_raw), 'forcingSha256': digest(raw)}
            if model.get('initializationPolicy') is not None:
                antecedent_raw = (old/'antecedent.json').read_bytes()
                if digest(antecedent_raw) != req.get('antecedentSha256'):
                    raise ValueError('LIVE_PREVIOUS_ANTECEDENT_INVALID')
                antecedent = json.loads(antecedent_raw)
        if model.get('initializationPolicy') is not None and antecedent is None:
            from .ingestion.antecedent import fetch as fetch_antecedent
            antecedent, antecedent_sources = fetch_antecedent(station, job['start'], os.environ.get('KMA_API_KEY', ''), heartbeat=lambda: renew(conn,job))
        renew(conn,job)
        extension, sources = observed_forcing(station, covered, job['end'], os.environ.get('KMA_API_KEY', ''), heartbeat=lambda: renew(conn,job))
        renew(conn,job)
        saved_depths = {v['end']: v['depthMm'] for v in observations[-60:]}
        if any(v['end'] in saved_depths and v['depthMm'] != saved_depths[v['end']]
               for v in extension['overlapObservations']):
            raise ValueError('AWS_PREVIOUS_INTERVAL_REVISED')
        evaporation = reusable_observation_hour(previous_evaporation, covered, job['end'])
        weather_sources = []
        if evaporation is None:
            evaporation, weather_sources = observed_evaporation(
                covered, job['end'], os.environ.get('KMA_API_KEY', ''), heartbeat=lambda: renew(conn,job))
        evaporation = append_evaporation(previous_evaporation, len(observations), model['hydrology']['evaporationMmDay'], evaporation)
        forcing = extension | {'start': job['start'].isoformat(),
                               'observations': observations+extension['observations'],
                               'sourceHashes': source_hashes+extension['sourceHashes'], 'previousInput': previous_ref,
                               'evaporation': evaporation}
        for raw, meta in sources+weather_sources+antecedent_sources:
            source_archive.store(root,path/(meta['sha256']+'.txt'),raw,meta['sha256'])
            (path/(meta['sha256']+'.json')).write_bytes(encode(meta))
        missing_sources = []
        antecedent_hashes = (antecedent['rainfall']['sourceHashes']+antecedent['evaporation']['sourceHashes']) if antecedent else []
        for sha in sorted(set(forcing['sourceHashes']+evaporation['sourceHashes']+antecedent_hashes)):
            if not re.fullmatch('[a-f0-9]{64}', sha):
                raise ValueError('LIVE_SOURCE_HASH_INVALID')
            for suffix in ('.txt','.json'):
                target = path/(sha+suffix)
                if not target.exists() and previous_directory is not None:
                    original = previous_directory/(sha+suffix)
                    if original.is_file() and original.resolve() == original.absolute():
                        expected = sha if suffix == '.txt' else previous_manifest.get(sha+suffix)
                        source_archive.link(original,target,expected)
            if not (path/(sha+'.txt')).is_file() or not (path/(sha+'.json')).is_file():
                missing_sources.append(sha)
        forcing['sourceArchive'] = {'complete': not missing_sources, 'missingHashes': missing_sources}
        # 저장된 값은 이 계산의 재현 입력이다. 최신 날씨 응답의 공급원으로 사용하지 않는다.
        model['rainfall'] = {k: forcing[k] for k in ('start', 'end', 'intervalSeconds', 'stationId', 'sourceHashes', 'evidence')}
        model['rainfall']['depthsMm'] = [v['depthMm'] for v in forcing['observations']]
        placement = {'cellId': job['installation']['cell_id'], 'facilityType': job['installation']['facility_type'],
                     'areaM2': float(job['installation']['area_m2'])}
        model = with_observed_forcing(model, evaporation)
        source, forcing_raw = encode(model), encode(forcing)
        request = {'schemaVersion': 1, 'installationId': str(job['installation']['id']),
                   'modelSha256': digest(source), 'forcingSha256': digest(forcing_raw),
                   'siteModelHash': job['installation']['model_hash'], 'placement': placement, 'engine': engine,
                   'weeklyRuleVersion': rule,
                   'scoreContext': comparison_context,
                   'weeklyCodeSha256': digest((Path(__file__).parent/'weekly.py').read_bytes())}
        if timed:
            request['installedAt'] = score_start.isoformat()
            request['installationClock'] = 'SERVER_SECOND_RESOLUTION_V1'
        if job['installation'].get('admission_snapshot') is not None:
            request['publicAssetPolicy'] = json.loads(job['installation']['admission_snapshot'])
        if job['installation'].get('cost_snapshot') is not None:
            request['costSnapshotRaw'] = job['installation']['cost_snapshot']
            request['costSnapshotSha256'] = job['installation']['cost_snapshot_sha256']
            request['installationCostKrw'] = str(job['installation']['cost'])
        if antecedent is not None:
            antecedent_raw = encode(antecedent)
            (path/'antecedent.json').write_bytes(antecedent_raw)
            request['antecedentSha256'] = digest(antecedent_raw)
        request_raw = encode(request)
        (path/'model-source.json').write_bytes(source)
        (path/'forcing.json').write_bytes(forcing_raw)
        (path/'request.json').write_bytes(request_raw)
        for module in ('engine/evapotranspiration.py', 'ingestion/evaporation.py', 'ingestion/daily_evaporation.py', 'ingestion/antecedent.py', 'ingestion/live.py', 'weekly.py'):
            (path/Path(module).name).write_bytes((Path(__file__).parent/module).read_bytes())
        env = {k: v for k, v in os.environ.items() if k in ('PATH', 'LANG', 'LC_ALL', 'LIVE_SWMM_LIBRARY','NATIVE_SPATIAL_CACHE')}
        env['PYTHONPATH'] = str(ROOT/'simulation')
        try:
            if run_process([sys.executable, '-m', 'waterleague_sim.run_live_job', str(path)],
                           env=env, timeout=90, heartbeat=lambda: renew(conn,job)) != 0:
                raise ValueError('LIVE_ENGINE_FAILED')
        except subprocess.TimeoutExpired:
            raise ValueError('LIVE_ENGINE_TIMEOUT') from None
        result = read_result(path/'result.json')
        if result.get('scoreContext') != comparison_context:
            raise ValueError('LIVE_SCORE_CONTEXT_INVALID')
        score_policy.verify(comparison_context, 'WEEKLY', rule)
        if previous_result is not None:
            # 어댑터 수정 후에도 기존 관측 구간의 최종 상태가 같아야 연속 결과를 게시한다.
            prefix_index = int((covered-job['start']).total_seconds()/60)-1
            for run in ('baseline','strategy'):
                if result[run]['samples'][prefix_index] != previous_result[run]['final']:
                    raise ValueError('LIVE_PREVIOUS_STATE_CHANGED')
        state = result['strategy']['final']
        public = {'stationId': station, 'stationName': station_name, 'simulationStart': score_start.isoformat(),
                  'simulatedThrough': job['end'].isoformat(), 'engineVersion': '5.2.4', 'validationLevel': 'EXPLORATORY',
                  **{k: state[k] for k in ('precipitationM3', 'infiltrationM3', 'evaporationM3', 'storageM3',
                                          'surfaceDepthMm', 'soilMoisture', 'storageDepthMm')},
                  'runoffM3': state['surfaceRunoffM3']+state['lidDrainageM3'],
                  'runoffContinuityPercent': result['strategy']['runoffContinuityPercent'],
                  'evaporationMethod': result['evaporation']['method'],
                  'initialState': result.get('initialization', {}).get('method', 'ASSUMED_DESIGN_START'),
                  'initialization': result.get('initialization'), 'facilityDesign': result.get('facilityDesign'),
                  'runoffComparison': result.get('runoffComparison'),
                  'designContract': result['designContract'],
                  'scoreContext': result['scoreContext'],
                  'lifeCycleCost': result['lifeCycleCost'],
                  'inflowPolicy': result['inflowPolicy'],
                  'cistern': result.get('cistern'),
                  'areaLimitBasis': model['cells'][0].get('areaLimitBasis','LEGACY_DESIGN_RATIO')}
        weeks = weekly_aggregate(result['contribution'], score_start, job['end'], max(covered, score_start), rule=rule)
        job['competition_frames'] = result['contribution']
        saved = finish(conn, job, public, digest(request_raw), None, weeks, digest((path/'manifest.json').read_bytes()))
    except Exception as e:
        code = str(e)
        if not re.fullmatch(r'(AWS|KMA|LIVE)_[A-Z_]{1,48}', code):
            code = 'LIVE_CALCULATION_FAILED'
        saved = finish(conn, job, None, None, code)
    return saved


def run_once(conn, root):
    job = claim(conn)
    if not job:
        return False
    process(conn, job, root)
    print('공동 시설 물리 계산', job['id'], flush=True)
    return True
