"""배포 DB의 역할 생성·명시적 권한 부여. 기존 비밀번호는 자동 변경하지 않음."""
from pathlib import Path
import sys

import psycopg
from psycopg import sql

TABLES = (
    'organizations accounts rate_limits strategies strategy_versions simulation_jobs submissions '
    'research_consents audit_events spring_session spring_session_attributes account_mfa '
    'queue_admission account_reviews leagues league_submissions rainfall_comparisons rainfall_comparison_jobs '
    'utilization_requests utilization_decisions strategy_reviews league_participants '
    'league_participant_events league_invitations league_teams league_team_members '
    'research_comparisons research_searches research_search_sources research_candidates shared_installations '
    'shared_physics_jobs historical_experiments'
).split()
MUTABLE_QUEUE_COLUMNS = 'state attempts lease_token lease_until finished_at error_code result'.split()


def connect(role):
    secret = Path('/run/secrets') / (role + '-password')
    password = secret.read_text().strip()
    if not password:
        raise ValueError('DB_SECRET_MISSING')
    return psycopg.connect(host='db', dbname='waterleague', user=role, password=password,
                          connect_timeout=10, autocommit=True)


def bootstrap():
    with connect('wl_admin') as db, db.transaction():
        for role in ('wl_owner', 'wl_api', 'wl_worker'):
            if not db.execute('SELECT 1 FROM pg_roles WHERE rolname=%s', (role,)).fetchone():
                password = (Path('/run/secrets') / (role + '-password')).read_text().strip()
                db.execute(sql.SQL('CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE '
                                   'NOREPLICATION NOBYPASSRLS PASSWORD {}')
                           .format(sql.Identifier(role), sql.Literal(password)))
        db.execute('ALTER DATABASE waterleague OWNER TO wl_owner')
        db.execute('REVOKE ALL ON DATABASE waterleague FROM PUBLIC')
        db.execute('REVOKE ALL ON SCHEMA public FROM PUBLIC')
        db.execute('ALTER SCHEMA public OWNER TO wl_owner')
        db.execute('GRANT CONNECT ON DATABASE waterleague TO wl_owner, wl_api, wl_worker')
    # 오래된 비밀 파일과 이미 존재하는 DB의 불일치는 재설정 대신 중단.
    for role in ('wl_owner', 'wl_api', 'wl_worker'):
        with connect(role) as db:
            flags = db.execute('SELECT rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls '
                               'FROM pg_roles WHERE rolname=current_user').fetchone()
            if any(flags):
                raise ValueError('DB_ROLE_UNSAFE')


def grant():
    with connect('wl_owner') as db, db.transaction():
        actual = {r[0] for r in db.execute("SELECT tablename FROM pg_tables WHERE schemaname='public'")}
        if actual != set(TABLES) | {'flyway_schema_history'}:
            raise ValueError('DB_PERMISSION_CATALOG_MISMATCH')
        db.execute('REVOKE ALL ON ALL TABLES IN SCHEMA public FROM PUBLIC, wl_api, wl_worker')
        for table in TABLES:
            columns = [r[0] for r in db.execute('SELECT column_name FROM information_schema.columns '
                                               "WHERE table_schema='public' AND table_name=%s", (table,))]
            db.execute(sql.SQL('REVOKE ALL PRIVILEGES({}) ON {} FROM PUBLIC,wl_api,wl_worker').format(
                sql.SQL(',').join(map(sql.Identifier, columns)), sql.Identifier(table)))
        db.execute('REVOKE ALL ON SCHEMA public FROM PUBLIC, wl_api, wl_worker')
        db.execute('GRANT USAGE ON SCHEMA public TO wl_api, wl_worker')
        db.execute(sql.SQL('GRANT SELECT,INSERT,UPDATE,DELETE ON {} TO wl_api')
                   .format(sql.SQL(',').join(map(sql.Identifier, (t for t in TABLES if t != 'shared_physics_jobs')))))
        db.execute('GRANT SELECT ON shared_physics_jobs TO wl_api')
        db.execute('GRANT SELECT ON shared_installations TO wl_worker')
        db.execute('GRANT UPDATE(id) ON shared_installations TO wl_worker')
        db.execute('GRANT SELECT,INSERT ON shared_physics_jobs TO wl_worker')
        db.execute('GRANT UPDATE(state,lease_until,finished_at,input_hash,result,error_code) ON shared_physics_jobs TO wl_worker')
        db.execute('GRANT SELECT ON simulation_jobs,research_candidates,historical_experiments,queue_admission TO wl_worker')
        db.execute('GRANT SELECT(id,placements) ON strategy_versions TO wl_worker')
        db.execute('GRANT UPDATE(id) ON queue_admission TO wl_worker')
        for table in ('simulation_jobs', 'research_candidates', 'historical_experiments'):
            db.execute(sql.SQL('GRANT UPDATE({}) ON {} TO wl_worker').format(
                sql.SQL(',').join(map(sql.Identifier, MUTABLE_QUEUE_COLUMNS)), sql.Identifier(table)))


if __name__ == '__main__':
    try:
        {'bootstrap': bootstrap, 'grant': grant}[sys.argv[1]]()
    except Exception:
        # 드라이버 예외와 SQL에 포함될 수 있는 비밀값은 출력하지 않음.
        print('DB_SETUP_FAILED', file=sys.stderr)
        sys.exit(1)
    print('DB_SETUP_OK')
