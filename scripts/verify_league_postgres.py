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
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from local_config import ROOT, load


def source_counts(db):
    if db.execute("SELECT to_regclass('public.simulation_jobs')").fetchone()[0] is None:
        return ('UNINITIALIZED',)
    return db.execute('SELECT (SELECT count(*) FROM simulation_jobs),(SELECT count(*) FROM submissions),'
                      '(SELECT count(*) FROM leagues),(SELECT count(*) FROM research_searches),'
                      '(SELECT count(*) FROM research_candidates)').fetchone()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--suite', choices=['guest-historical', 'historical-submit-design', 'historical-design-run', 'historical-design', 'public-surface', 'infrastructure', 'league', 'analysis', 'queue', 'budget', 'physics', 'weekly', 'historical', 'watershed', 'cistern-plan', 'shared-research', 'search', 'restore', 'all'], default='league')
    suite = parser.parse_args().suite
    test_class = {'guest-historical': 'GuestHistoricalTests,HistoricalWorkflowTests,HistoricalSubmissionTests,ApiSecurityTests','historical-submit-design': 'HistoricalSubmissionTests,HistoricalDesignTests,ApiSecurityTests',
                  'historical-design-run': 'HistoricalDesignTests,HistoricalWorkflowTests,HistoricalSubmissionTests,ApiSecurityTests',
                  'historical-design': 'HistoricalDesignTests,HistoricalWorkflowTests,HistoricalSubmissionTests,ApiSecurityTests',
                  'public-surface': 'PublicSurfaceTests,SurfacePlaybackTests,ApiSecurityTests',
                  'infrastructure': 'InfrastructureCatalogTests,ApiSecurityTests,EquipmentHistoryTests',
                  'league': 'LeagueParticipationWorkflowTests',
                  'analysis': 'ResearchAnalysisWorkflowTests',
                  'queue': 'QueueCapacityTests',
                  'budget': 'BudgetAllocationTests,BudgetLedgerWorkflowTests,SharedInstallationTests,HistoricalWorkflowTests',
                  'physics': 'PhysicsWorkflowTests,SharedInstallationTests',
                  'weekly': 'WeeklyWorkflowTests',
                  'historical': 'HistoricalWorkflowTests,HistoricalSubmissionTests',
                  'watershed': 'WatershedWorkflowTests',
                  'cistern-plan': 'CisternMapPlanTests,CisternLayoutTests',
                  'shared-research': 'SharedResearchWorkflowTests',
                  'search': 'ResearchSearchWorkflowTests',
                  'restore': 'ResearchSearchWorkflowTests#replaysActualSwmmSourcesAndGeneratedCandidateBundleOnIsolatedPostgres',
                  'all': 'LeagueParticipationWorkflowTests,ResearchAnalysisWorkflowTests,ResearchSearchWorkflowTests'}[suite]
    load()
    config = conninfo_to_dict(os.environ['DATABASE_URL'])
    if config.get('host') not in {'127.0.0.1', 'localhost', '::1'}:
        raise SystemExit('로컬 PostgreSQL만 허용')
    prefix = {'guest-historical': 'waterleague_queue_test_','historical-submit-design': 'waterleague_queue_test_', 'historical-design-run': 'waterleague_queue_test_', 'queue': 'waterleague_queue_test_', 'physics': 'waterleague_queue_test_', 'historical': 'waterleague_queue_test_', 'watershed': 'waterleague_queue_test_', 'search': 'waterleague_search_test_',
              'restore': 'waterleague_search_test_'}
    test_name = prefix.get(suite, 'waterleague_league_test_') + uuid.uuid4().hex
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
            before = source_counts(db)
            db.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(test_name)))
            created = True
        with path.open('x') as log:
            path.chmod(0o600)
            physical = ['-Dwaterleague.integration.python=' + sys.executable] if suite in {'search', 'restore'} else []
            if suite == 'guest-historical':
                physical.append('-Dwaterleague.integration.guest.fixture=' + str(path.with_suffix('.guest.json')))
            if suite == 'historical':
                physical.append('-Dwaterleague.integration.historical.request=' + str(path.with_suffix('.request.json')))
            if suite in {'historical-design', 'historical-design-run'}:
                physical.append('-Dwaterleague.integration.design.fixture=' + str(path.with_suffix('.design.json')))
            if suite == 'historical-submit-design':
                physical.append('-Dwaterleague.integration.submission.design.fixture=' + str(path.with_suffix('.submission.json')))
            if suite == 'historical-design-run':
                physical.append('-Dwaterleague.integration.design.run.fixture=' + str(path.with_suffix('.requests.json')))
            if suite == 'restore':
                physical.append('-Dwaterleague.integration.restore=true')
            result = subprocess.run(
                [str(ROOT / 'backend/mvnw'), '--batch-mode', '-Dtest=' + test_class,
                 '-Dwaterleague.integration.jdbc=' + jdbc, *physical, 'test'],
                cwd=ROOT / 'backend', env=env, stdout=log, stderr=subprocess.STDOUT, timeout=180)
            if suite in {'historical-design', 'historical-design-run'} and result.returncode == 0:
                result = subprocess.run(
                    [str(ROOT / 'backend/mvnw'), '--batch-mode', '-Dtest=HistoricalDesignRestartTests',
                     '-Dwaterleague.integration.jdbc=' + jdbc, *physical, 'test'],
                    cwd=ROOT / 'backend', env=env, stdout=log, stderr=subprocess.STDOUT, timeout=180)
            if suite in {'guest-historical', 'queue', 'physics', 'historical', 'watershed', 'historical-design-run', 'historical-submit-design'} and result.returncode == 0:
                worker_env = env | {'WL_WORKER_TEST_DSN': make_conninfo(**(config | {'dbname': test_name})),
                                    'PYTHONPATH': str(ROOT / 'simulation')}
                if suite == 'guest-historical':
                    worker_env['WL_GUEST_FIXTURE'] = str(path.with_suffix('.guest.json'))
                    worker_env['WL_GUEST_EVIDENCE'] = str(path.with_suffix('.guest-runs'))
                if suite == 'historical-submit-design':
                    worker_env['WL_SUBMISSION_DESIGN_FIXTURE'] = str(path.with_suffix('.submission.json'))
                    worker_env['WL_SUBMISSION_DESIGN_EVIDENCE'] = str(path.with_suffix('.runs'))
                if suite == 'historical-design-run':
                    worker_env['WL_DESIGN_RUN_FIXTURE'] = str(path.with_suffix('.requests.json'))
                    worker_env['WL_DESIGN_RUN_EVIDENCE'] = str(path.with_suffix('.runs'))
                pattern = ['-p', {'guest-historical':'test_guest_historical.py','historical-submit-design':'test_saved_submission.py','historical-design-run':'test_historical_design_run.py','physics':'test_shared_physics.py','historical':'test_historical.py','watershed':'test_watershed.py'}[suite]] if suite in {'guest-historical','physics','historical','watershed','historical-design-run','historical-submit-design'} else []
                result = subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', 'integration', *pattern, '-v'],
                    cwd=ROOT / 'simulation', env=worker_env, stdout=log, stderr=subprocess.STDOUT, timeout=240)
        with psycopg.connect(**config) as db:
            after = source_counts(db)
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
