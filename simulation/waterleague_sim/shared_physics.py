"""공동 설치 관측 구간의 원자적 임대·연속 재생·상태 게시."""
import json
import os
import re
import signal
import subprocess
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from .engine.continuous import ROOT, digest, engine_identity
from .ingestion.live import observed_forcing
from .shared_model import resolve


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
            WHERE date_trunc('minute',LEAST(COALESCE(i.removed_at,clock_timestamp()),clock_timestamp()-interval '2 minutes'))
                > date_trunc('minute',i.installed_at)+CASE WHEN i.installed_at=date_trunc('minute',i.installed_at)
                    THEN interval '0 minutes' ELSE interval '1 minute' END
              AND NOT EXISTS(SELECT 1 FROM shared_physics_jobs j WHERE j.installation_id=i.id AND j.state='RUNNING')
              AND NOT EXISTS(SELECT 1 FROM shared_physics_jobs j WHERE j.installation_id=i.id AND j.created_at>clock_timestamp()-interval '60 seconds')
              AND NOT EXISTS(SELECT 1 FROM shared_physics_jobs j WHERE j.installation_id=i.id AND j.state='SUCCEEDED'
                AND j.requested_through>=date_trunc('minute',LEAST(COALESCE(i.removed_at,clock_timestamp()),clock_timestamp()-interval '2 minutes')))
            ORDER BY (SELECT max(j.created_at) FROM shared_physics_jobs j WHERE j.installation_id=i.id) NULLS FIRST,i.installed_at,i.id
            FOR UPDATE OF i SKIP LOCKED LIMIT 1
            """).fetchone()
        if not installation:
            return None
        # 설치 행 잠금 뒤 새 스냅샷으로 중복 임대 여부를 다시 확인한다.
        if conn.execute("SELECT 1 FROM shared_physics_jobs WHERE installation_id=%s AND (state='RUNNING' OR created_at>clock_timestamp()-interval '60 seconds')",
                        (installation['id'],)).fetchone():
            return None
        previous = conn.execute("""SELECT * FROM shared_physics_jobs WHERE installation_id=%s AND state='SUCCEEDED'
            ORDER BY requested_through DESC,created_at DESC LIMIT 1""", (installation['id'],)).fetchone()
        start = floor_minute(installation['installed_at'])
        if start < installation['installed_at']:
            start += timedelta(minutes=1)
        covered = previous['requested_through'] if previous else start
        now = conn.execute('SELECT clock_timestamp() AS now').fetchone()['now']
        end = min(floor_minute(now)-timedelta(minutes=2), covered+timedelta(hours=23))
        if installation['removed_at']:
            end = min(end, floor_minute(installation['removed_at']))
        if end <= covered:
            return None
        job = {'id': uuid.uuid4(), 'lease_token': uuid.uuid4(), 'installation': installation,
               'start': start, 'end': end, 'previous': previous}
        conn.execute("""INSERT INTO shared_physics_jobs(id,installation_id,simulation_start,requested_through,
            state,lease_token,lease_until,created_at) VALUES(%s,%s,%s,%s,'RUNNING',%s,clock_timestamp()+interval '240 seconds',clock_timestamp())""",
            (job['id'], installation['id'], start, end, job['lease_token']))
        return job


def finish(conn, job, result, input_hash, error):
    with conn.transaction():
        conn.execute('SELECT id FROM shared_physics_jobs WHERE id=%s FOR UPDATE', (job['id'],)).fetchone()
        return conn.execute("""UPDATE shared_physics_jobs SET state=%s,result=%s,input_hash=%s,error_code=%s,
            finished_at=clock_timestamp(),lease_until=NULL WHERE id=%s AND state='RUNNING'
            AND lease_token=%s AND lease_until>clock_timestamp()""",
            ('SUCCEEDED' if result is not None else 'FAILED', json.dumps(result, ensure_ascii=False, allow_nan=False) if result else None,
             input_hash, error, job['id'], job['lease_token'])).rowcount == 1


def process(conn, job, root):
    path = Path(root)/'shared-physics'/str(job['id'])/str(job['lease_token'])
    path.mkdir(parents=True, exist_ok=False)
    try:
        model, station, station_name = resolve(job['installation'])
        engine = engine_identity()
        observations, source_hashes, previous_ref = [], [], None
        covered = job['start']
        if previous := job['previous']:
            old = Path(root)/'shared-physics'/str(previous['id'])/str(previous['lease_token'])
            raw = (old/'forcing.json').read_bytes()
            req_raw = (old/'request.json').read_bytes()
            req = json.loads(req_raw)
            forcing = json.loads(raw)
            if (digest(req_raw) != previous['input_hash'] or digest(raw) != req['forcingSha256']
                    or req['engine'] != engine or req['installationId'] != str(job['installation']['id'])
                    or forcing['stationId'] != station or datetime.fromisoformat(forcing['start']) != job['start']
                    or datetime.fromisoformat(forcing['end']) != previous['requested_through']):
                raise ValueError('LIVE_PREVIOUS_INPUT_INVALID')
            observations, source_hashes = forcing['observations'], forcing['sourceHashes']
            covered = previous['requested_through']
            previous_ref = {'jobId': str(previous['id']), 'leaseToken': str(previous['lease_token']),
                            'requestSha256': digest(req_raw), 'forcingSha256': digest(raw)}
        extension, sources = observed_forcing(station, covered, job['end'], os.environ.get('KMA_API_KEY', ''))
        saved_depths = {v['end']: v['depthMm'] for v in observations[-60:]}
        if any(v['end'] in saved_depths and v['depthMm'] != saved_depths[v['end']]
               for v in extension['overlapObservations']):
            raise ValueError('AWS_PREVIOUS_INTERVAL_REVISED')
        forcing = extension | {'start': job['start'].isoformat(),
                               'observations': observations+extension['observations'],
                               'sourceHashes': source_hashes+extension['sourceHashes'], 'previousInput': previous_ref}
        for raw, meta in sources:
            (path/(meta['sha256']+'.txt')).write_bytes(raw)
            (path/(meta['sha256']+'.json')).write_bytes(encode(meta))
        # 저장된 값은 이 계산의 재현 입력이다. 최신 날씨 응답의 공급원으로 사용하지 않는다.
        model['rainfall'] = {k: forcing[k] for k in ('start', 'end', 'intervalSeconds', 'stationId', 'sourceHashes', 'evidence')}
        model['rainfall']['depthsMm'] = [v['depthMm'] for v in forcing['observations']]
        placement = {'cellId': job['installation']['cell_id'], 'facilityType': job['installation']['facility_type'],
                     'areaM2': float(job['installation']['area_m2'])}
        source, forcing_raw = encode(model), encode(forcing)
        request = {'schemaVersion': 1, 'installationId': str(job['installation']['id']),
                   'modelSha256': digest(source), 'forcingSha256': digest(forcing_raw),
                   'siteModelHash': job['installation']['model_hash'], 'placement': placement, 'engine': engine}
        request_raw = encode(request)
        (path/'model-source.json').write_bytes(source)
        (path/'forcing.json').write_bytes(forcing_raw)
        (path/'request.json').write_bytes(request_raw)
        env = {k: v for k, v in os.environ.items() if k in ('PATH', 'LANG', 'LC_ALL', 'LIVE_SWMM_LIBRARY')}
        env['PYTHONPATH'] = str(ROOT/'simulation')
        child = subprocess.Popen([sys.executable, '-m', 'waterleague_sim.run_live_job', str(path)],
                                 env=env, start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            if child.wait(timeout=90) != 0:
                raise ValueError('LIVE_ENGINE_FAILED')
        except subprocess.TimeoutExpired:
            os.killpg(child.pid, signal.SIGKILL)
            child.wait()
            raise ValueError('LIVE_ENGINE_TIMEOUT') from None
        result = json.loads((path/'result.json').read_text())
        state = result['strategy']['final']
        public = {'stationId': station, 'stationName': station_name, 'simulationStart': job['start'].isoformat(),
                  'simulatedThrough': job['end'].isoformat(), 'engineVersion': '5.2.4', 'validationLevel': 'EXPLORATORY',
                  **{k: state[k] for k in ('precipitationM3', 'infiltrationM3', 'evaporationM3', 'storageM3',
                                          'surfaceDepthMm', 'soilMoisture', 'storageDepthMm')},
                  'runoffM3': state['surfaceRunoffM3']+state['lidDrainageM3'],
                  'runoffContinuityPercent': result['strategy']['runoffContinuityPercent'],
                  'evaporationMethod': result['evaporation']['method'], 'initialState': 'ASSUMED_DESIGN_START'}
        saved = finish(conn, job, public, digest(request_raw), None)
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
