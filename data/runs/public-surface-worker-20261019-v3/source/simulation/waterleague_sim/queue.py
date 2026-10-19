"""개인 계산과 연구 후보의 공용 입장 잠금·lease·결과 fencing."""
import json
import uuid

from psycopg import sql

TABLES = {'PERSONAL': 'simulation_jobs', 'RESEARCH_CANDIDATE': 'research_candidates', 'HISTORICAL': 'historical_experiments', 'WATERSHED': 'watershed_experiments'}


def table(kind):
    # 요청값이나 DB 문자열을 SQL 식별자로 직접 사용하지 않는다.
    if kind not in TABLES:
        raise ValueError('지원하지 않는 계산 큐')
    return sql.Identifier(TABLES[kind])


def claim(conn):
    with conn.transaction():
        if not conn.execute('SELECT id FROM queue_admission WHERE id=1 FOR UPDATE').fetchone():
            raise RuntimeError('공용 큐 입장 잠금 누락')
        choices = []
        for kind in TABLES:
            target = table(kind)
            conn.execute(sql.SQL("""
                UPDATE {} SET state='FAILED',error_code='WORKER_RETRY_EXHAUSTED',
                    finished_at=clock_timestamp(),lease_until=NULL
                WHERE id IN (SELECT id FROM {} WHERE state='RUNNING'
                    AND lease_until<=clock_timestamp() AND attempts>=3 FOR UPDATE SKIP LOCKED)
                """).format(target, target))
            if kind == 'PERSONAL':
                query = sql.SQL("""
                    SELECT j.*,v.placements FROM {} j
                    JOIN strategy_versions v ON v.id=j.version_id
                    """).format(target)
            else:
                query = sql.SQL('SELECT j.* FROM {} j ').format(target)
            job = conn.execute(query + sql.SQL("""
                WHERE (j.state='QUEUED' OR (j.state='RUNNING' AND j.lease_until<=clock_timestamp()))
                    AND j.attempts<3 ORDER BY j.created_at,j.id
                FOR UPDATE OF j SKIP LOCKED LIMIT 1
                """)).fetchone()
            if job:
                choices.append(job | {'queue_kind': kind})
        if not choices:
            return None
        job = min(choices, key=lambda j: (j['created_at'], j['queue_kind'], str(j['id'])))
        token = uuid.uuid4()
        conn.execute(sql.SQL("""
            UPDATE {} SET state='RUNNING',attempts=attempts+1,lease_token=%s,
                lease_until=clock_timestamp()+interval '180 seconds',finished_at=NULL,
                error_code=NULL,result=NULL WHERE id=%s
            """).format(table(job['queue_kind'])), (token, job['id']))
        return job | {'lease_token': token, 'attempts': job['attempts'] + 1}


def finish(conn, job, state, result, error):
    if state not in {'SUCCEEDED', 'FAILED', 'REJECTED'}:
        raise ValueError('잘못된 계산 완료 상태')
    encoded = json.dumps(result, ensure_ascii=False, allow_nan=False) if result is not None else None
    with conn.transaction():
        # 행 잠금 대기가 끝난 실제 시각으로 lease를 재검사한다.
        conn.execute(sql.SQL('SELECT id FROM {} WHERE id=%s FOR UPDATE')
                     .format(table(job['queue_kind'])), (job['id'],)).fetchone()
        count = conn.execute(sql.SQL("""
            UPDATE {} SET state=%s,result=%s,error_code=%s,finished_at=clock_timestamp(),lease_until=NULL
            WHERE id=%s AND state='RUNNING' AND lease_token=%s AND lease_until>clock_timestamp()
            """).format(table(job['queue_kind'])),
            (state, encoded, error, job['id'], job['lease_token'])).rowcount
    return count == 1
