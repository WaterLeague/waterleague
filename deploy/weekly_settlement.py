"""원 계산을 보존한 주간 말단 결측 정산과 작업 선택."""
import hashlib
import json
import os
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from waterleague_sim.shared_physics import floor_minute, process
from waterleague_sim.engine.continuous import digest
from waterleague_sim.evaluation import score_policy
from waterleague_sim.weekly import SECOND_POLICY
from waterleague_sim.ingestion import request_store, source_archive
from waterleague_sim.ingestion.live import KST, observed_forcing
from waterleague_sim.installation_model import resolve

RULE = 'CLOSED_WEEK_MISSING_SUFFIX_V1'
GAP_ERRORS = {'AWS_REQUIRED_MINUTE_MISSING', 'SEOUL_RAIN_POSITIVE_SCORE_GAP',
              'SEOUL_RAIN_REQUIRED_INTERVAL_MISSING'}

def claim(conn):
    policy_hash = digest(score_policy.verified_policy()[0])
    with conn.transaction():
        conn.execute("""UPDATE shared_physics_jobs SET state='FAILED',error_code='LIVE_LEASE_EXPIRED',
            finished_at=clock_timestamp(),lease_until=NULL WHERE state='RUNNING' AND lease_until<=clock_timestamp()""")
        installation = conn.execute("""
            SELECT i.* FROM shared_installations i
            WHERE i.source_retired_at IS NULL
              AND NOT EXISTS(SELECT 1 FROM weekly_observation_exclusions e WHERE e.installation_id=i.id
                AND e.excluded_from<=COALESCE((SELECT max(p.requested_through) FROM shared_physics_jobs p
                  WHERE p.installation_id=i.id AND p.state='SUCCEEDED'),date_trunc('minute',i.installed_at)))
              AND date_trunc('minute',LEAST(COALESCE(i.removed_at,i.season_ends_at,clock_timestamp()),date_bin(interval '5 minutes',clock_timestamp()-interval '2 minutes',timestamptz '2000-01-01 00:00:00+00')))
                > date_trunc('minute',i.installed_at)+CASE WHEN i.installed_at=date_trunc('minute',i.installed_at)
                    OR i.physics_policy='INSTALLATION_SECOND_V2' THEN interval '0 minutes' ELSE interval '1 minute' END
              AND NOT EXISTS(SELECT 1 FROM shared_physics_jobs j WHERE j.installation_id=i.id AND j.state='RUNNING')
              AND NOT EXISTS(SELECT 1 FROM shared_physics_jobs j WHERE j.installation_id=i.id AND j.created_at>clock_timestamp()-interval '60 seconds')
              AND NOT EXISTS(SELECT 1 FROM shared_physics_jobs j WHERE j.installation_id=i.id AND j.state='FAILED'
                AND COALESCE(j.finished_at,j.created_at)>clock_timestamp()-interval '5 minutes')
              AND NOT EXISTS(SELECT 1 FROM shared_physics_jobs j WHERE j.installation_id=i.id AND j.state='SUCCEEDED'
                AND j.requested_through>=date_trunc('minute',LEAST(COALESCE(i.removed_at,i.season_ends_at,clock_timestamp()),date_bin(interval '5 minutes',clock_timestamp()-interval '2 minutes',timestamptz '2000-01-01 00:00:00+00'))))
            ORDER BY (i.competition_id IS NULL AND COALESCE(i.removed_at,i.season_ends_at)<=clock_timestamp()) DESC NULLS LAST,
                EXISTS(SELECT 1 FROM shared_weekly_scores s WHERE s.installation_id=i.id
                AND s.score_policy_sha256<>%s) DESC,
                (SELECT max(j.created_at) FROM shared_physics_jobs j WHERE j.installation_id=i.id) NULLS FIRST,i.installed_at,i.id
            FOR UPDATE OF i SKIP LOCKED LIMIT 1
            """, (policy_hash,)).fetchone()
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
        current = floor_minute(now)-timedelta(minutes=2)
        current -= timedelta(minutes=current.minute % 5)
        end = min(current, covered+timedelta(hours=23))
        if stops := installation['removed_at'] or installation.get('season_ends_at'):
            end = min(end, floor_minute(stops))
        exclusion = conn.execute('SELECT excluded_from FROM weekly_observation_exclusions WHERE installation_id=%s',
            (installation['id'],)).fetchone()
        if exclusion:
            end = min(end, exclusion['excluded_from'])
        if end <= covered:
            return None
        job = {'id': uuid.uuid4(), 'lease_token': uuid.uuid4(), 'installation': installation,
               'start': start, 'end': end, 'previous': previous}
        conn.execute("""INSERT INTO shared_physics_jobs(id,installation_id,simulation_start,requested_through,
            state,lease_token,lease_until,created_at) VALUES(%s,%s,%s,%s,'RUNNING',%s,clock_timestamp()+interval '240 seconds',clock_timestamp())""",
            (job['id'], installation['id'], start, end, job['lease_token']))
        return job


def missing_suffix(observations, start, end):
    minute = timedelta(minutes=1)
    times = {datetime.fromisoformat(row['end']) for row in observations}
    expected = int((end-start).total_seconds()/60)
    if len(times) != len(observations) or not 0 < expected <= 10080:
        raise ValueError('WEEKLY_EXCLUSION_RANGE_INVALID')
    if any(at <= start or at > end or at.second or at.microsecond for at in times):
        raise ValueError('WEEKLY_EXCLUSION_RANGE_INVALID')
    missing = [start+minute*n for n in range(1, expected+1) if start+minute*n not in times]
    if not missing or any(at > missing[0] for at in times):
        return None
    return missing[0]-minute


def register_missing_suffix(conn, job, root, fetcher=observed_forcing):
    installation = job['installation']
    until = installation.get('season_ends_at')
    now = conn.execute('SELECT clock_timestamp() AS now').fetchone()['now']
    if (installation.get('competition_id') is not None or until is None
            or now < until+timedelta(hours=2)
            or installation.get('removed_at') and installation['removed_at'] < until):
        return False
    start = job['previous']['requested_through'] if job['previous'] else job['start']
    _, station, _ = resolve(installation)
    rain, sources = fetcher(station, start, until, os.environ.get('KMA_API_KEY', ''),
        share_ranges=True, verified_zero_gaps=True, allow_gaps=True)
    cut = missing_suffix(rain['observations'], start, until)
    if cut is None:
        return False
    week = (until.astimezone(KST)-timedelta(days=7)).date()
    identifier = uuid.uuid4()
    directory = Path(root).resolve()/'weekly-exclusions'/str(identifier)
    directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    metadata = []
    for raw, source in sources:
        sha = source['sha256']
        source_archive.store(root, directory/(sha+'.txt'), raw, sha)
        metadata.append(source)
    evidence = {'ruleVersion': RULE, 'installationId': str(installation['id']),
        'settlementCodeSha256': digest(Path(__file__).read_bytes()),
        'stationId': station, 'checkedAt': now.isoformat(), 'queryStart': start.isoformat(),
        'queryEnd': until.isoformat(), 'excludedFrom': cut.isoformat(),
        'excludedUntil': until.isoformat(), 'observedPrefixMinutes': int((cut-start).total_seconds()/60),
        'missingMinutes': int((until-cut).total_seconds()/60), 'sources': metadata}
    raw = (json.dumps(evidence, ensure_ascii=False, sort_keys=True)+'\n').encode()
    (directory/'evidence.json').write_bytes(raw)
    (directory/'settlement-rule.py').write_bytes(Path(__file__).read_bytes())
    with conn.transaction():
        conn.execute('SELECT id FROM shared_installations WHERE id=%s FOR UPDATE', (installation['id'],)).fetchone()
        latest = conn.execute("SELECT max(requested_through) AS through FROM shared_physics_jobs WHERE installation_id=%s AND state='SUCCEEDED'", (installation['id'],)).fetchone()['through']
        # 뒤늦게 도착한 성공 계산이나 다른 임대가 있으면 제외 결정을 게시하지 않는다.
        if latest and latest > cut or conn.execute("SELECT 1 FROM shared_physics_jobs WHERE installation_id=%s AND state='RUNNING'", (installation['id'],)).fetchone():
            return False
        inserted = conn.execute('''INSERT INTO weekly_observation_exclusions
            (id,installation_id,week_start,excluded_from,excluded_until,station_id,evidence_sha256,evidence,rule_version)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s) ON CONFLICT(installation_id,week_start) DO NOTHING''',
            (identifier,installation['id'],week,cut,until,station,hashlib.sha256(raw).hexdigest(),raw.decode(),RULE)).rowcount
    return inserted == 1


def run_once(conn, root):
    if not request_store.available(os.environ.get('KMA_API_KEY', '')):
        return False
    job = claim(conn)
    if job is None:
        return False
    process(conn, job, root)
    state = conn.execute('SELECT state,error_code FROM shared_physics_jobs WHERE id=%s', (job['id'],)).fetchone()
    if state['state'] == 'FAILED' and state['error_code'] in GAP_ERRORS:
        try:
            if register_missing_suffix(conn, job, root):
                print('WEEKLY_MISSING_SUFFIX_REGISTERED', str(job['installation']['id']), flush=True)
        except Exception:
            print('WEEKLY_EXCLUSION_NOT_CONFIRMED', flush=True)
    return True
