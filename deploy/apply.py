"""단일 운영 호스트의 잠금·암호화 백업·마이그레이션·복귀 처리."""
import base64
import datetime
import fcntl
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import time

BASE = Path('/opt/waterleague')
STATE = BASE / 'state'
UID = 10001


def private(path, value, owner=0):
    if path.is_symlink():
        raise ValueError('STATE_SYMLINK_REJECTED')
    path.write_text(value)
    path.chmod(0o600)
    os.chown(path, owner, owner)


def command(args, **kwargs):
    result = subprocess.run(args, capture_output=True, **kwargs)
    if result.returncode:
        private(BASE / 'deploy-failure.log', result.stdout.decode(errors='replace') + result.stderr.decode(errors='replace') if isinstance(result.stdout, bytes) else result.stdout + result.stderr)
        raise RuntimeError('DEPLOY_STEP_FAILED: ' + args[0])
    return result.stdout


def compose(release, *args, **kwargs):
    return command(['docker', 'compose', '--env-file', str(release / 'release.env'), '-f',
                    str(release / 'compose.yml'), '-f', str(release / 'compose.public.yml'), *args], **kwargs)


def backup(release):
    backups = BASE / 'backups'
    backups.mkdir(mode=0o700, exist_ok=True)
    identity = BASE / 'backup-identity.age'
    if not identity.exists():
        command(['age-keygen', '-o', str(identity)])
        identity.chmod(0o600)
    recipient = command(['age-keygen', '-y', str(identity)], text=True).strip()
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    target = backups / (stamp + '-' + release.name[:12] + '.tar.gz.age')
    pending = target.with_suffix(target.suffix + '.partial')
    with tempfile.TemporaryDirectory(prefix='backup-', dir=BASE) as directory:
        dump = Path(directory) / 'database.dump'
        with dump.open('wb') as output:
            result = subprocess.run(['docker', 'compose', '--env-file', str(release / 'release.env'),
                '-f', str(release / 'compose.yml'), 'exec', '-T', 'db', 'pg_dump', '-U', 'wl_admin',
                '-d', 'waterleague', '--format=custom', '--no-owner', '--no-acl'], stdout=output, stderr=subprocess.PIPE)
        if result.returncode or dump.stat().st_size == 0:
            raise RuntimeError('DATABASE_BACKUP_FAILED')
        external = STATE / 'cache/external-requests'
        extra = ['state/cache/external-requests'] if external.is_dir() and not external.is_symlink() else []
        # 반복되는 관측·계산 JSON을 먼저 압축해 암호화 백업의 공간 사용을 줄인다.
        archive = subprocess.Popen(['tar', '--use-compress-program=gzip -1', '-cf', '-', '-C', directory, 'database.dump',
            '-C', str(BASE), 'state/secrets', 'state/artifacts', 'releases/' + release.name, *extra], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        encrypted = subprocess.run(['age', '-r', recipient, '-o', str(pending)], stdin=archive.stdout, capture_output=True)
        archive.stdout.close()
        archive.communicate()
        if encrypted.returncode or archive.returncode:
            pending.unlink(missing_ok=True)
            raise RuntimeError('ENCRYPTED_BACKUP_FAILED')
    pending.chmod(0o600)
    pending.replace(target)
    for old in sorted([*backups.glob('*.tar.age'), *backups.glob('*.tar.gz.age')])[:-7]:
        if old.is_file() and not old.is_symlink():
            old.unlink()
    print('ENCRYPTED_BACKUP_OK', flush=True)


def main():
    revision = sys.argv[1]
    if os.getuid() != 0 or not re.fullmatch('[0-9a-f]{40}', revision):
        raise ValueError('DEPLOY_IDENTITY_INVALID')
    os.umask(0o077)
    BASE.mkdir(mode=0o700, exist_ok=True)
    lock = (BASE / 'deploy.lock').open('w')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    runtime = json.loads(Path('runtime.json').read_text())
    Path('runtime.json').unlink()
    if runtime['revision'] != revision or set(runtime['images']) != {'api', 'worker', 'web'}:
        raise ValueError('RELEASE_INVALID')
    for service, image in runtime['images'].items():
        if not re.fullmatch(f'ghcr.io/waterleague/waterleague-{service}@sha256:[0-9a-f]{{64}}', image):
            raise ValueError('IMAGE_REFERENCE_INVALID')
    if not shutil.which('age'):
        raise ValueError('AGE_INSTALLATION_REQUIRED')
    if shutil.disk_usage(BASE).free < 8 * 1024**3:
        raise ValueError('DISK_SPACE_INSUFFICIENT')
    for directory in (STATE, *(STATE / name for name in ('secrets', 'artifacts', 'cache', 'caddy-data', 'caddy-config'))):
        directory.mkdir(mode=0o700, exist_ok=True)
        os.chown(directory, UID, UID)
    secret_dir = STATE / 'secrets'
    roles = ('wl_admin', 'wl_owner', 'wl_api', 'wl_worker')
    stable = [*(role + '-password' for role in roles), 'database-url', 'mfa-key']
    exists = [(secret_dir / name).exists() for name in stable]
    if any(exists) and not all(exists):
        raise ValueError('PERSISTENT_SECRETS_INCOMPLETE')
    if not any(exists):
        values = {role + '-password': secrets.token_urlsafe(36) for role in roles}
        values['mfa-key'] = base64.b64encode(secrets.token_bytes(32)).decode()
        values['database-url'] = 'postgresql://wl_worker:' + values['wl_worker-password'] + '@db:5432/waterleague'
        for name, value in values.items():
            private(secret_dir / name, value, UID)
    (BASE / 'releases').mkdir(mode=0o700, exist_ok=True)
    release = BASE / 'releases' / revision
    release.mkdir(mode=0o700, exist_ok=True)
    for name in ('compose.yml', 'compose.public.yml'):
        shutil.copyfile(name, release / name)
    env = {'WL_PROJECT': 'waterleague', 'WL_STATE_DIR': str(STATE), 'WL_RUNTIME_UID': str(UID), 'WL_RUNTIME_GID': str(UID)}
    env.update({'WL_' + name.upper() + '_IMAGE': image for name, image in runtime['images'].items()})
    private(release / 'release.env', ''.join(k + '=' + v + '\n' for k, v in env.items()))
    current = BASE / 'current'
    previous = current.resolve() if current.is_symlink() else None
    # 레지스트리 토큰은 다운로드 동안만 존재하며 서버에 지속 로그인하지 않는다.
    with tempfile.TemporaryDirectory(prefix='registry-', dir=BASE) as registry:
        os.environ['DOCKER_CONFIG'] = registry
        command(['docker', 'login', 'ghcr.io', '-u', runtime['registryUser'], '--password-stdin'],
                input=runtime.pop('registryToken'), text=True)
        for image in runtime['images'].values():
            command(['docker', 'pull', image])
    os.environ.pop('DOCKER_CONFIG', None)
    stopped = False
    try:
        if previous:
            compose(previous, 'stop', 'web', 'api', 'worker')
            stopped = True
            backup(previous)
        for source, name in {'ADMIN_USERNAME': 'admin-username', 'ADMIN_PASSWORD': 'admin-password',
                             'DISCORD_WEBHOOK_URL': 'discord-webhook-url', 'KMA_API_KEY': 'kma-api-key',
                             'UPSTAGE_API_KEY': 'upstage-api-key'}.items():
            value = runtime['secrets'][source]
            if not isinstance(value, str) or not value:
                raise ValueError('RUNTIME_SECRET_MISSING')
            private(secret_dir / name, value, UID)
        # 이전 릴리스로 복귀해도 폐기한 키를 다시 사용하지 않도록 빈 파일만 남긴다.
        retired = secret_dir / 'kma-api-key-backup'
        if retired.exists():
            private(retired, '', UID)
        compose(release, 'up', '-d', '--no-build', '--wait', '--wait-timeout', '120', 'db')
        for service in ('bootstrap', 'migrate', 'grant', 'admin'):
            compose(release, 'run', '--rm', '--no-deps', '-T', service)
            print(service.upper() + '_OK', flush=True)
        compose(release, 'up', '-d', '--no-build', '--no-deps', '--wait', '--wait-timeout', '240', 'api', 'worker', 'web')
        for attempt in range(30):
            check = subprocess.run(['curl', '--fail', '--silent', '--show-error', '--max-time', '10',
                '--resolve', 'waterleague.cloud:443:127.0.0.1', 'https://waterleague.cloud/api/v1/health'], capture_output=True)
            if check.returncode == 0:
                break
            time.sleep(5)
        else:
            raise RuntimeError('PUBLIC_TLS_HEALTH_FAILED')
        pending = BASE / 'current.next'
        pending.unlink(missing_ok=True)
        pending.symlink_to(release, target_is_directory=True)
        pending.replace(current)
        print('DEPLOYED ' + revision, flush=True)
    except Exception:
        if previous and stopped:
            compose(previous, 'up', '-d', '--no-build', '--no-deps', '--wait', '--wait-timeout', '240', 'api', 'worker', 'web')
            print('PREVIOUS_RELEASE_RESTORED', flush=True)
        raise
    finally:
        (secret_dir / 'admin-password').unlink(missing_ok=True)
        (secret_dir / 'admin-username').unlink(missing_ok=True)
    # 새 릴리스의 정상 시작을 확인한 뒤 이전 Secret 마운트 파일을 제거한다.
    (secret_dir / 'kma-api-key-backup').unlink(missing_ok=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(type(error).__name__ + ': DEPLOYMENT_FAILED', file=sys.stderr)
        sys.exit(1)
