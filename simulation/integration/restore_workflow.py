"""격리 HTTP·SWMM 기록의 연구 계보와 DB/산출물 사본 복원 검증."""
import argparse
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit
from unittest.mock import patch

import psycopg
from psycopg.conninfo import make_conninfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import verify_database_restore as restore


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--jdbc', required=True)
    parser.add_argument('--artifacts', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    args = parser.parse_args()
    target = urlsplit(args.jdbc.removeprefix('jdbc:'))
    name = target.path.removeprefix('/')
    if (target.scheme != 'postgresql' or target.hostname not in {'127.0.0.1', 'localhost', '::1'}
            or target.username or target.password or target.query or target.fragment
            or not re.fullmatch(r'waterleague_search_test_[a-f0-9]{32}', name)):
        raise SystemExit('격리 탐색 시험 DB만 허용')
    dsn = make_conninfo(host=target.hostname, port=target.port, dbname=name,
                       user=os.environ['WL_INTEGRATION_USER'], password=os.environ['WL_INTEGRATION_PASSWORD'])
    root = args.artifacts.resolve()
    os.environ.update(DATABASE_URL=dsn, ARTIFACTS_PATH=str(root))
    tool_path = Path('/Applications/Postgres.app/Contents/Versions/18/bin' if sys.platform == 'darwin'
                     else '/usr/lib/postgresql/18/bin')
    if (tool_path / 'pg_dump').is_file():
        os.environ['PG_BIN'] = str(tool_path)
    with psycopg.connect(dsn, autocommit=True) as conn:
        with conn.transaction():
            conn.execute("SET TIME ZONE 'UTC'")
            before = restore.table_fingerprints(conn)
            original = restore.check_artifacts(conn, root)
        assert original['succeededJobs'] == original['succeededCandidates'] == 2
        assert original['verifiedFiles'] == 72 and original['generation']['searches'] == 1
        assert conn.execute('SELECT count(*) FROM research_consents WHERE granted').fetchone()[0] == 0
        for statement in [
            'UPDATE research_candidates SET cost=cost+1',
            "UPDATE research_searches SET provenance_hash=repeat('0',64)",
            'DELETE FROM research_search_sources WHERE job_id=(SELECT min(job_id::text)::uuid FROM research_search_sources)',
        ]:
            with conn.transaction():
                conn.execute(statement)
                try:
                    restore.check_artifacts(conn, root)
                except (restore.RestoreCheckError, ValueError):
                    pass
                else:
                    raise AssertionError('손상된 연구 기록의 복원 검사 통과')
                raise psycopg.Rollback()
        with conn.transaction():
            conn.execute("UPDATE research_candidates SET state='FAILED',result=NULL WHERE arm='UNIFORM'")
            partial = restore.check_artifacts(conn, root)
            assert partial['succeededCandidates'] == 1 and partial['generation']['candidates'] == 2
            assert partial['verifiedFiles'] == 54
            raise psycopg.Rollback()
        with conn.transaction():
            assert before == restore.table_fingerprints(conn)
    report_path = args.work / 'restore-report.json'
    with patch.object(sys, 'argv', ['verify_database_restore.py', '--report', str(report_path)]):
        restore.main()
    report = json.loads(report_path.read_text())
    assert report['status'] == 'PASS' and report['temporaryDatabaseRemoved']
    assert report['temporaryArtifactCopiesRemoved']
    assert report['artifactMode'] == 'COPY_AND_VERIFY_ISOLATED_FILES'
    assert report['artifacts'] == original
    with psycopg.connect(dsn) as conn:
        conn.execute("SET TIME ZONE 'UTC'")
        assert before == restore.table_fingerprints(conn)
        assert conn.execute('SELECT count(*) FROM pg_database WHERE datname=%s',
                            (report['database'],)).fetchone()[0] == 0
    print('연구 원본 2개·후보 2개·72개 파일 사본 복원, 철회 상태 보존, 손상/부분 완료 검사 통과')


if __name__ == '__main__':
    main()
