"""임시 PostgreSQL DB에서 참가·연구 분석 API와 경합 시험."""
from pathlib import Path
import json
import os
import subprocess
import sys
import uuid
import argparse
import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict
from local_config import ROOT, load


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--suite', choices=['league', 'analysis', 'all'], default='league')
    suite = parser.parse_args().suite
    test_class = {'league': 'LeagueParticipationWorkflowTests',
                  'analysis': 'ResearchAnalysisWorkflowTests',
                  'all': 'LeagueParticipationWorkflowTests,ResearchAnalysisWorkflowTests'}[suite]
    load()
    config = conninfo_to_dict(os.environ['DATABASE_URL'])
    if config.get('host') not in {'127.0.0.1', 'localhost', '::1'}:
        raise SystemExit('로컬 PostgreSQL만 허용')
    test_name = 'waterleague_league_test_' + uuid.uuid4().hex
    path = ROOT / 'tmp' / (test_name + '.log')
    path.parent.mkdir(exist_ok=True)
    env = {k: v for k, v in os.environ.items() if k in {'PATH', 'HOME', 'JAVA_HOME', 'TMPDIR', 'LANG', 'LC_ALL'}}
    if sys.platform == 'darwin':
        env['JAVA_HOME'] = subprocess.check_output(['/usr/libexec/java_home', '-v', '25'], text=True).strip()
    java = str(Path(env['JAVA_HOME']) / 'bin/java') if env.get('JAVA_HOME') else 'java'
    version = subprocess.run([java, '-version'], env=env, capture_output=True, text=True, check=True)
    if 'version \"25.' not in version.stderr and 'version \"25\"' not in version.stderr:
        raise SystemExit('Java 25 런타임 필요')
    env['WL_INTEGRATION_USER'] = config['user']
    env['WL_INTEGRATION_PASSWORD'] = config.get('password', '')
    host = config['host']
    host = f'[{host}]' if ':' in host else host
    jdbc = f"jdbc:postgresql://{host}:{config.get('port', '5432')}/{test_name}"
    created = False
    try:
        with psycopg.connect(**config, autocommit=True) as db:
            before = db.execute('SELECT (SELECT count(*) FROM simulation_jobs),(SELECT count(*) FROM submissions),(SELECT count(*) FROM leagues)').fetchone()
            db.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(test_name)))
            created = True
        with path.open('x') as log:
            path.chmod(0o600)
            result = subprocess.run(
                [str(ROOT / 'backend/mvnw'), '--batch-mode', '-Dtest=' + test_class,
                 '-Dwaterleague.integration.jdbc=' + jdbc, 'test'],
                cwd=ROOT / 'backend', env=env, stdout=log, stderr=subprocess.STDOUT, timeout=180)
        with psycopg.connect(**config) as db:
            after = db.execute('SELECT (SELECT count(*) FROM simulation_jobs),(SELECT count(*) FROM submissions),(SELECT count(*) FROM leagues)').fetchone()
        if before != after:
            raise RuntimeError('원본 자료 수 변경 확인 필요')
        print(json.dumps({'passed': result.returncode == 0, 'sourceCountsUnchanged': True, 'log': str(path)}, ensure_ascii=False))
        if result.returncode:
            raise SystemExit(result.returncode)
    finally:
        if created:
            with psycopg.connect(**config, autocommit=True) as db:
                db.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(test_name)))


if __name__ == '__main__':
    main()
