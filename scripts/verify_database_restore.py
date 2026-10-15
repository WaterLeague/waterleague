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
from decimal import Decimal

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from local_config import ROOT, load

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


def check_artifacts(conn, root):
    rows = conn.execute('''select j.id,j.model_hash,j.input_hash,j.result,v.placements,
        v.model_hash,v.input_hash,v.cost,v.currency from simulation_jobs j
        join strategy_versions v on v.id=j.version_id where j.state='SUCCEEDED' order by j.id''')
    count, files, hashes = 0, 0, hashlib.sha256()
    for job_id, model_hash, input_hash, raw_result, raw_placements, vm, vi, cost, currency in rows:
        require(model_hash == vm and input_hash == vi, '계산·저장 버전 식별값 불일치')
        require(hashlib.sha256((model_hash + '\n' + raw_placements).encode()).hexdigest()
                == input_hash, '배치 원문 hash 불일치')
        result = json.loads(raw_result)
        token = str(uuid.UUID(result['artifactToken']))
        folder = root / str(job_id) / token
        require(not (root / str(job_id)).is_symlink() and not folder.is_symlink(), '산출물 경로 링크 거부')
        manifest_path = folder / 'manifest.json'
        manifest_hash = digest(manifest_path)
        manifest = json.loads(manifest_path.read_text())
        require(set(manifest) == FILES, '재현 manifest 파일 구성 불일치')
        for name, expected in manifest.items():
            require(isinstance(expected, str) and re.fullmatch('[a-f0-9]{64}', expected), '파일 hash 형식 오류')
            require(digest(folder / name) == expected, '재현 파일 hash 불일치')
            files += 1
        model = json.loads((folder / 'model-source.json').read_text())
        require(digest(folder / 'model-source.json') == model_hash, '원본 모델 hash 불일치')
        require(json.loads((folder / 'placements.json').read_text()) == json.loads(raw_placements), '배치 내용 불일치')
        stored = json.loads((folder / 'result.json').read_text())
        require(all(result.get(k) == v for k, v in stored.items()), 'DB·파일 계산 결과 불일치')
        require(result['modelHash'] == model_hash and result['inputHash'] == input_hash, '결과 식별값 불일치')
        amount = sum(Decimal(str(p['areaM2'])) * Decimal(str(model['unitCosts'][p['facilityType']]))
                     for p in json.loads(raw_placements))
        require(amount == cost, '저장 비용·배치 단가 불일치')
        require(currency != 'KRW' or model.get('currency') == 'KRW', '원화 통화 불일치')
        base = Decimal(str(result['baseline']['accountedDischargeM3']))
        design = Decimal(str(result['strategy']['accountedDischargeM3']))
        require(base > 0, '점수 기준 유출량 오류')
        expected_score = 100 * (base - design) / base
        require(abs(expected_score - Decimal(str(result['score']))) < Decimal('0.0000001'), '서버 점수 재계산 불일치')
        hashes.update(f'{job_id}:{token}:{manifest_hash}\n'.encode())
        count += 1
    for score, raw in conn.execute('select s.score,j.result from submissions s join simulation_jobs j on j.id=s.job_id'):
        require(abs(score - Decimal(str(json.loads(raw)['score']))) < Decimal('0.0000001'), '공개 제출 점수 불일치')
    return {'succeededJobs': count, 'verifiedFiles': files, 'artifactIndexSha256': hashes.hexdigest()}


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
    report = {'scope': 'LOCAL_LOGICAL_RESTORE_DRILL', 'status': 'FAILED', 'database': restore_name,
              'excludes': sorted(EPHEMERAL), 'artifactMode': 'VERIFY_EXISTING_FILES_ONLY'}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    require(not args.report.exists(), '기존 보고서 덮어쓰기 거부')
    try:
        with tempfile.TemporaryDirectory(prefix='waterleague-restore-') as temporary:
            dump = Path(temporary) / 'database.dump'
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
                artifact_before = check_artifacts(source, Path(os.environ.get('ARTIFACTS_PATH', ROOT / 'data/runs')).resolve())
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
                artifact_after = check_artifacts(restored, Path(os.environ.get('ARTIFACTS_PATH', ROOT / 'data/runs')).resolve())
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
        report['elapsedSeconds'] = round(time.monotonic() - started, 3)
        with args.report.open('x') as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
        if cleanup_error:
            raise cleanup_error
    print('격리 복원·테이블 hash·계산 산출물 대조 통과:', len(report['tables']), '개 테이블,',
          report['artifacts']['succeededJobs'], '개 완료 계산,', report['elapsedSeconds'], '초')


if __name__ == '__main__':
    try:
        main()
    except RestoreCheckError as error:
        print('복원 검사 실패:', error, file=sys.stderr)
        sys.exit(1)
    except Exception as error:
        print('복원 검사 실패:', type(error).__name__, '(원문 비공개)', file=sys.stderr)
        sys.exit(1)
