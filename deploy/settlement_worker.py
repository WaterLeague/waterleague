"""일반 계산 큐와 주간 결측 정산 큐의 공통 실행 진입점."""
import sys
import time
import psycopg
from psycopg.rows import dict_row
from waterleague_sim import worker
from waterleague_sim.runtime import database_url
from waterleague_sim.spatial.play_bundle import open_catalog
from weekly_settlement import run_once


def main():
    open_catalog()
    with psycopg.connect(database_url(), autocommit=True, row_factory=dict_row) as connection:
        while True:
            job = worker.claim(connection)
            if job:
                worker.process(connection, job)
            shared = run_once(connection, worker.ARTIFACTS)
            if '--once' in sys.argv:
                return
            if not job and not shared:
                time.sleep(2)


if __name__ == '__main__':
    main()
