"""격리 HTTP 통합 시험에서 지정한 작업만 실제 워커로 계산."""
import argparse
import os
from pathlib import Path
from urllib.parse import urlsplit
import uuid

import psycopg
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row
from psycopg import sql


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--jdbc', required=True)
    parser.add_argument('--artifacts', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--kind', choices=['PERSONAL', 'RESEARCH_CANDIDATE'], required=True)
    parser.add_argument('ids', nargs='+', type=uuid.UUID)
    args = parser.parse_args()
    target = urlsplit(args.jdbc.removeprefix('jdbc:'))
    name = target.path.removeprefix('/')
    if (target.scheme != 'postgresql' or target.hostname not in {'127.0.0.1', 'localhost', '::1'}
            or not name.startswith('waterleague_search_test_')
            or len(name.removeprefix('waterleague_search_test_')) != 32):
        raise SystemExit('격리 탐색 시험 DB만 허용')
    int(name.removeprefix('waterleague_search_test_'), 16)
    os.environ['DATABASE_URL'] = make_conninfo(
        host=target.hostname, port=target.port, dbname=name,
        user=os.environ['WL_INTEGRATION_USER'], password=os.environ['WL_INTEGRATION_PASSWORD'])
    os.environ['ARTIFACTS_PATH'] = str(args.artifacts.resolve())
    os.environ['SIMULATION_CACHE_PATH'] = str(args.work.resolve() / 'cache')
    from waterleague_sim.worker import process
    from waterleague_sim.queue import claim, TABLES
    with psycopg.connect(os.environ['DATABASE_URL'], autocommit=True, row_factory=dict_row) as db:
        # 다른 시나리오의 대기 작업은 건드리지 않고 이 시험 작업을 먼저 선택한다.
        table = sql.Identifier(TABLES[args.kind])
        changed = db.execute(sql.SQL("UPDATE {} SET created_at='2000-01-01T00:00:00Z' "
                                     "WHERE id=ANY(%s) AND state='QUEUED'").format(table), (args.ids,))
        assert changed.rowcount == len(args.ids)
        remaining = set(args.ids)
        while remaining:
            job = claim(db)
            assert job and job['queue_kind'] == args.kind and job['id'] in remaining
            assert process(db, job)
            state = db.execute(sql.SQL('SELECT state FROM {} WHERE id=%s').format(table), (job['id'],)).fetchone()
            assert state['state'] == 'SUCCEEDED'
            remaining.remove(job['id'])


if __name__ == '__main__':
    main()
