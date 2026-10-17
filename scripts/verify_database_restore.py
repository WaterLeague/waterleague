"""공유 스냅샷의 논리 덤프를 새 임시 DB에 복원하고 기록·산출물 대조."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from decimal import Decimal, ROUND_HALF_UP

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from local_config import ROOT, load

sys.path.insert(0, str(ROOT / 'simulation'))
from waterleague_sim.model_catalog import read_catalog
from waterleague_sim.optimization.replay import decoded, number, verify as verify_generation

EPHEMERAL = {'spring_session', 'spring_session_attributes', 'rate_limits'}
FILES = {'builder.py', 'model-source.json', 'model.json', 'placements.json', 'request.json',
         'result.json', *(f'{case}.{ext}' for case in ['baseline', 'strategy', 'low', 'high']
                          for ext in ['inp', 'rpt', 'out'])}


class RestoreCheckError(Exception):
    pass


def require(value, message):
    if not value:
        raise RestoreCheckError(message)


def digest(path, max_bytes=64 * 1024 * 1024):
    require(path.is_file() and not path.is_symlink(), '산출물 파일 누락 또는 링크 거부')
    require(path.stat().st_size <= max_bytes, '파일 크기 상한 초과')
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def table_fingerprints(conn):
    names = [row[0] for row in conn.execute(
        "select tablename from pg_tables where schemaname='public' order by tablename")]
    result = {}
    for name in names:
        if name in EPHEMERAL:
            continue
        # UTC·C 정렬로 세션 로케일 차이를 제거하고 원문은 보고서에 남기지 않는다.
        query = sql.SQL('select record_text from (select row_to_json(t)::text as record_text '
                        'from public.{} t) records order by record_text COLLATE "C"').format(sql.Identifier(name))
        sha, count = hashlib.sha256(), 0
        with conn.cursor(name='fingerprint_' + uuid.uuid4().hex) as cursor:
            cursor.execute(query)
            for row in cursor:
                sha.update(row[0].encode() + b'\n')
                count += 1
        result[name] = {'rows': count, 'sha256': sha.hexdigest()}
    return result


def score(result):
    base = number(result['baseline']['accountedDischargeM3'])
    design = number(result['strategy']['accountedDischargeM3'])
    require(base > 0, '점수 기준 유출량 오류')
    calculated = 100 * (base - design) / base
    require(abs(calculated - number(result['score'])) < Decimal('0.0000001'), '서버 점수 재계산 불일치')
    return calculated.quantize(Decimal('0.00000001'), rounding=ROUND_HALF_UP)


def check_generation(conn):
    rows = conn.execute('''select id,model_hash,budget_krw,seed,top_k,candidates_per_arm,
        provenance,provenance_hash from research_searches order by id''').fetchall()
    models = read_catalog(ROOT / 'data/models') if rows else {}
    hashes, count = hashlib.sha256(), 0
    for search_id, model_hash, budget, seed, top, wanted, raw, provenance_hash in rows:
        require(hashlib.sha256(raw.encode()).hexdigest() == provenance_hash, '생성 계보 원문 hash 불일치')
        require(model_hash in models, '연구 모델 원문 누락')
        generation = verify_generation(models[model_hash], decoded(raw))
        require(generation['settings'] == {'budgetKrw': budget, 'seed': seed,
                'topK': top, 'candidatesPerArm': wanted}, '생성 설정·DB 불일치')
        sources = conn.execute('''select j.id,j.version_id,j.model_hash,j.input_hash,j.state,j.result,
            v.placements,v.cost,v.currency from research_search_sources x
            join simulation_jobs j on j.id=x.job_id join strategy_versions v on v.id=j.version_id
            where x.search_id=%s order by j.id''', (search_id,)).fetchall()
        by_id = {str(row[0]): row for row in sources}
        expected_ids = {s['sample']['jobId'] for s in generation['sources']}
        require(set(by_id) == expected_ids and len(sources) == len(expected_ids), '생성 원본 연결 불일치')
        for source in generation['sources']:
            sample = source['sample']
            _, version, model, input_hash, state, raw_result, placements, cost, currency = by_id[sample['jobId']]
            require(state == 'SUCCEEDED' and model == model_hash and currency == 'KRW', '생성 원본 상태·모델·통화 오류')
            require(str(version) == sample['versionId'] and input_hash == sample['inputHash']
                    and placements == sample['placementsSource'] and cost == sample['costKrw']
                    and score(decoded(raw_result)) == sample['score'], '생성 원본·저장 기록 불일치')
        candidates = conn.execute('''select arm,ordinal,placements,model_hash,input_hash,cost
            from research_candidates where search_id=%s order by arm,ordinal''', (search_id,)).fetchall()
        expected = {(c['arm'], c['ordinal']): c for c in generation['candidates']}
        require(len(candidates) == len(expected), '생성 후보 수 불일치')
        seen = set()
        for arm, ordinal, placements, model, input_hash, cost in candidates:
            key = (arm, ordinal)
            require(key in expected and key not in seen, '생성 후보 방법·순번 불일치')
            candidate = expected[key]
            require(model == model_hash and input_hash == candidate['inputHash']
                    and placements == candidate['placementsSource'] and cost == candidate['costKrw'],
                    '생성 후보·저장 기록 불일치')
            seen.add(key)
        count += len(candidates)
        hashes.update(f'{search_id}:{provenance_hash}\n'.encode())
    return {'searches': len(rows), 'candidates': count, 'generationIndexSha256': hashes.hexdigest()}


def check_one_artifact(root, kind, job_id, model_hash, input_hash, raw_result,
                       raw_placements, cost, currency, copy_to=None):
    require(kind in {'PERSONAL', 'RESEARCH_CANDIDATE'}, '계산 종류 오류')
    require(hashlib.sha256((model_hash + '\n' + raw_placements).encode()).hexdigest()
            == input_hash, '배치 원문 hash 불일치')
    result = decoded(raw_result)
    token = str(uuid.UUID(result['artifactToken']))
    require(token == result['artifactToken'], '산출물 token 형식 오류')
    parts = ([] if kind == 'PERSONAL' else ['research-candidates']) + [str(uuid.UUID(str(job_id))), token]
    folder = root
    require(root.is_dir() and not root.is_symlink(), '산출물 루트 누락 또는 링크 거부')
    for part in parts:
        folder = folder / part
        require(folder.is_dir() and not folder.is_symlink(), '산출물 경로 누락 또는 링크 거부')
    manifest_path = folder / 'manifest.json'
    manifest_hash = digest(manifest_path)
    manifest = decoded(manifest_path.read_bytes())
    require(set(manifest) == FILES, '재현 manifest 파일 구성 불일치')
    for name, expected in manifest.items():
        require(isinstance(expected, str) and re.fullmatch('[a-f0-9]{64}', expected), '파일 hash 형식 오류')
        require(digest(folder / name) == expected, '재현 파일 hash 불일치')
    model = decoded((folder / 'model-source.json').read_bytes())
    placements = decoded(raw_placements)
    require(digest(folder / 'model-source.json') == model_hash, '원본 모델 hash 불일치')
    require(decoded((folder / 'placements.json').read_bytes()) == placements, '배치 내용 불일치')
    require(decoded((folder / 'request.json').read_bytes()) == {
        'modelHash': model_hash, 'inputHash': input_hash, 'placements': placements}, '계산 요청 내용 불일치')
    stored = decoded((folder / 'result.json').read_bytes())
    require(result == stored | {'artifactToken': token, 'modelHash': model_hash, 'inputHash': input_hash},
            'DB·파일 계산 결과 불일치')
    amount = sum(number(p['areaM2']) * number(model['unitCosts'][p['facilityType']]) for p in placements)
    require(amount == cost, '저장 비용·배치 단가 불일치')
    require(currency != 'KRW' or model.get('currency') == 'KRW', '원화 통화 불일치')
    score(result)
    if copy_to is not None:
        target = copy_to.joinpath(*parts)
        target.mkdir(mode=0o700, parents=True, exist_ok=False)
        # 복사 중 변한 원본도 기존 manifest와 대조하여 불완전 사본을 거부한다.
        for name, expected in sorted((manifest | {'manifest.json': manifest_hash}).items()):
            require(shutil.disk_usage(target).free > (folder / name).stat().st_size + 128 * 1024**2,
                    '산출물 임시 사본 공간 부족')
            with (folder / name).open('rb') as source, (target / name).open('xb') as output:
                shutil.copyfileobj(source, output)
            require(digest(target / name) == expected, '산출물 사본 hash 불일치')
    return f'{kind}:{job_id}:{token}:{manifest_hash}\n'.encode()


def check_artifacts(conn, root, copy_to=None):
    generation = check_generation(conn)
    rows = conn.execute('''select j.id,j.model_hash,j.input_hash,j.result,v.placements,
        v.model_hash,v.input_hash,v.cost,v.currency from simulation_jobs j
        join strategy_versions v on v.id=j.version_id where j.state='SUCCEEDED' order by j.id''')
    count, candidate_count, hashes = 0, 0, hashlib.sha256()
    for job_id, model_hash, input_hash, raw_result, raw_placements, vm, vi, cost, currency in rows:
        require(model_hash == vm and input_hash == vi, '계산·저장 버전 식별값 불일치')
        hashes.update(check_one_artifact(root, 'PERSONAL', job_id, model_hash, input_hash,
            raw_result, raw_placements, cost, currency, copy_to))
        count += 1
    for job_id, model_hash, input_hash, raw_result, placements, cost in conn.execute('''
            select id,model_hash,input_hash,result,placements,cost from research_candidates
            where state='SUCCEEDED' order by id'''):
        hashes.update(check_one_artifact(root, 'RESEARCH_CANDIDATE', job_id, model_hash, input_hash,
            raw_result, placements, cost, 'KRW', copy_to))
        candidate_count += 1
    for score, raw in conn.execute('select s.score,j.result from submissions s join simulation_jobs j on j.id=s.job_id'):
        require(abs(score - number(decoded(raw)['score'])) < Decimal('0.0000001'), '공개 제출 점수 불일치')
    return {'succeededJobs': count, 'succeededCandidates': candidate_count,
            'verifiedFiles': (count+candidate_count)*len(FILES),
            'artifactIndexSha256': hashes.hexdigest(), 'generation': generation}


def tool_env(dsn):
    values = conninfo_to_dict(dsn)
    allowed = {'host', 'hostaddr', 'port', 'user', 'password', 'dbname', 'sslmode',
               'sslrootcert', 'sslcert', 'sslkey', 'connect_timeout'}
    require(set(values) <= allowed and values.get('dbname'), '지원하지 않는 DB 접속 옵션')
    host = values.get('host', '')
    require(host in ('', 'localhost', '127.0.0.1', '::1') or host.startswith('/'), '로컬 DB만 복원 훈련 가능')
    require(values.get('hostaddr', '127.0.0.1') in ('127.0.0.1', '::1'), '로컬 DB 주소만 허용')
    env = {k: os.environ[k] for k in ['PATH', 'LANG', 'LC_ALL', 'TMPDIR'] if k in os.environ}
    for key, var in {'host': 'PGHOST', 'hostaddr': 'PGHOSTADDR', 'port': 'PGPORT',
                     'user': 'PGUSER', 'password': 'PGPASSWORD', 'dbname': 'PGDATABASE',
                     'sslmode': 'PGSSLMODE', 'sslrootcert': 'PGSSLROOTCERT',
                     'sslcert': 'PGSSLCERT', 'sslkey': 'PGSSLKEY'}.items():
        if key in values:
            env[var] = values[key]
    env['PGCONNECT_TIMEOUT'] = '10'
    return env


def run_tool(executable, args, env):
    result = subprocess.run([executable, *args], env=env, capture_output=True, timeout=300)
    require(result.returncode == 0, Path(executable).name + ' 실패; 비밀 보호를 위해 원문 로그 생략')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, default=ROOT / 'tmp/restore-check.json')
    args = parser.parse_args()
    os.umask(0o077)
    load()
    dsn = os.environ.get('DATABASE_URL')
    require(dsn, 'DATABASE_URL 설정 필요')
    bin_dir = os.environ.get('PG_BIN')
    tools = {name: str(Path(bin_dir) / name) if bin_dir else shutil.which(name)
             for name in ['pg_dump', 'pg_restore']}
    require(all(path and Path(path).is_file() for path in tools.values()), 'PG_BIN에 PostgreSQL 도구 디렉터리 설정 필요')
    restore_name = 'waterleague_restore_' + uuid.uuid4().hex
    require(conninfo_to_dict(dsn).get('dbname') != restore_name, '원본 DB 사용 거부')
    restore_dsn = make_conninfo(dsn, dbname=restore_name)
    env = tool_env(dsn)
    started = time.monotonic()
    created = False
    artifact_copy = None
    report = {'scope': 'LOCAL_LOGICAL_RESTORE_DRILL', 'status': 'FAILED', 'database': restore_name,
              'excludes': sorted(EPHEMERAL), 'artifactMode': 'COPY_AND_VERIFY_ISOLATED_FILES'}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    require(not args.report.exists(), '기존 보고서 덮어쓰기 거부')
    try:
        with tempfile.TemporaryDirectory(prefix='waterleague-restore-') as temporary:
            dump = Path(temporary) / 'database.dump'
            artifact_copy = Path(temporary) / 'artifacts'
            with psycopg.connect(dsn, connect_timeout=10) as source:
                source.execute('set transaction isolation level repeatable read read only')
                source.execute("set time zone 'UTC'")
                major = source.info.server_version // 10000
                require(major >= 18, '검증 대상 PostgreSQL major 불일치')
                for executable in tools.values():
                    version = subprocess.run([executable, '--version'], env=env, capture_output=True, timeout=10)
                    match = re.search(rb'PostgreSQL\) (\d+)\.', version.stdout)
                    require(version.returncode == 0 and match and int(match[1]) == major, '서버·복원 도구 major 불일치')
                size = source.execute('select pg_database_size(current_database())').fetchone()[0]
                require(shutil.disk_usage(temporary).free > size * 4 + 512 * 1024 * 1024, '임시 덤프 공간 부족')
                snapshot = source.execute('select pg_export_snapshot()').fetchone()[0]
                before = table_fingerprints(source)
                artifact_before = check_artifacts(source, Path(os.environ.get('ARTIFACTS_PATH', ROOT / 'data/runs')),
                                                  copy_to=artifact_copy)
                run_tool(tools['pg_dump'], ['--format=custom', '--no-password', '--snapshot=' + snapshot,
                    '--file=' + str(dump), *(f'--exclude-table-data=public.{name}' for name in sorted(EPHEMERAL))], env)
                require(dump.stat().st_mode & 0o077 == 0, '임시 덤프 권한 오류')
            with psycopg.connect(dsn, autocommit=True, connect_timeout=10) as control:
                control.execute(sql.SQL('create database {} template template0').format(sql.Identifier(restore_name)))
                created = True
            report['dumpSha256'] = digest(dump, 8 * 1024 * 1024 * 1024)
            run_tool(tools['pg_restore'], ['--no-password', '--no-owner', '--no-acl', '--exit-on-error',
                '--single-transaction', '--dbname=' + restore_name, str(dump)], env)
            with psycopg.connect(restore_dsn, connect_timeout=10) as restored:
                restored.execute("set time zone 'UTC'")
                after = table_fingerprints(restored)
                require(before == after, '복원 테이블 건수·hash 불일치')
                require(restored.execute('select count(*) from flyway_schema_history where not success').fetchone()[0] == 0, '실패한 이관 기록')
                for name in EPHEMERAL:
                    require(restored.execute(sql.SQL('select count(*) from {}').format(sql.Identifier(name))).fetchone()[0] == 0, '복원 후 임시 세션 잔존')
                artifact_after = check_artifacts(restored, artifact_copy)
                require(artifact_before == artifact_after, '복원 산출물 인덱스 불일치')
            report.update(status='PASS', postgresMajor=major, tables=after, artifacts=artifact_after)
    finally:
        cleanup_error = None
        if created:
            try:
                with psycopg.connect(dsn, autocommit=True, connect_timeout=10) as control:
                    # 호출자가 지정한 이름이나 원본 DB를 삭제할 수 없도록 생성된 이름만 사용한다.
                    control.execute(sql.SQL('drop database {}').format(sql.Identifier(restore_name)))
            except Exception:
                report['status'] = 'CLEANUP_REQUIRED'
                cleanup_error = RestoreCheckError('임시 DB 정리 필요: ' + restore_name)
        report['temporaryDatabaseCreated'] = created
        report['temporaryDatabaseRemoved'] = created and cleanup_error is None
        report['temporaryArtifactCopiesRemoved'] = artifact_copy is not None and not artifact_copy.exists()
        report['elapsedSeconds'] = round(time.monotonic() - started, 3)
        with args.report.open('x') as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
        if cleanup_error:
            raise cleanup_error
    print('격리 복원·테이블 hash·계산 산출물 대조 통과:', len(report['tables']), '개 테이블,',
          report['artifacts']['succeededJobs'], '개 개인 계산,', report['artifacts']['succeededCandidates'],
          '개 연구 후보,', report['elapsedSeconds'], '초')


if __name__ == '__main__':
    try:
        main()
    except RestoreCheckError as error:
        print('복원 검사 실패:', error, file=sys.stderr)
        sys.exit(1)
    except Exception as error:
        print('복원 검사 실패:', type(error).__name__, '(원문 비공개)', file=sys.stderr)
        sys.exit(1)
