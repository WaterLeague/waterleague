"""GitHub의 운영 비밀을 출력하지 않고 ARM64 이미지와 배포 묶음 전달."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def run(*args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def validate():
    required = ('OCI_HOST', 'OCI_USER', 'OCI_SSH_KEY', 'OCI_KNOWN_HOSTS', 'ADMIN_USERNAME',
                'ADMIN_PASSWORD', 'DISCORD_WEBHOOK_URL', 'KMA_API_KEY')
    missing = [key for key in required if not os.environ.get(key, '').strip()]
    if missing:
        raise ValueError('MISSING_SECRETS: ' + ', '.join(missing))
    if os.environ['OCI_HOST'] != '168.107.61.81' or not re.fullmatch(r'[a-z_][a-z0-9_-]{0,31}', os.environ['OCI_USER']):
        raise ValueError('OCI_TARGET_INVALID')
    if not re.fullmatch(r'[a-z0-9_]{4,32}', os.environ['ADMIN_USERNAME']):
        raise ValueError('ADMIN_USERNAME_INVALID')
    if not 16 <= len(os.environ['ADMIN_PASSWORD']) <= 128 or '\x00' in os.environ['ADMIN_PASSWORD']:
        raise ValueError('ADMIN_PASSWORD_INVALID')
    if not re.fullmatch(r'https://discord\.com/api/(?:v10/)?webhooks/[0-9]{10,25}/[A-Za-z0-9_-]{40,200}', os.environ['DISCORD_WEBHOOK_URL']):
        raise ValueError('DISCORD_WEBHOOK_INVALID')


def build():
    sha = os.environ['GITHUB_SHA']
    if not re.fullmatch('[0-9a-f]{40}', sha):
        raise ValueError('REVISION_INVALID')
    images = {}
    with tempfile.TemporaryDirectory(prefix='wl-registry-') as directory:
        env = os.environ | {'DOCKER_CONFIG': directory}
        run('docker', 'login', 'ghcr.io', '-u', os.environ['GITHUB_ACTOR'], '--password-stdin',
            input=os.environ['GHCR_TOKEN'], text=True, env=env, stdout=subprocess.DEVNULL)
        for service in ('api', 'worker', 'web'):
            tag = f'ghcr.io/waterleague/waterleague-{service}:{sha}'
            run('docker', 'build', '--platform', 'linux/arm64', '--label',
                'org.opencontainers.image.source=https://github.com/WaterLeague/waterleague',
                '--label', f'org.opencontainers.image.revision={sha}', '-f', f'deploy/{service}.Dockerfile', '-t', tag, '.', env=env)
            run('docker', 'push', tag, env=env)
            digests = json.loads(subprocess.check_output(['docker', 'inspect', '--format', '{{json .RepoDigests}}', tag], env=env))
            images[service] = next(d for d in digests if d.startswith(f'ghcr.io/waterleague/waterleague-{service}@sha256:'))
    (ROOT / 'tmp').mkdir(exist_ok=True)
    (ROOT / 'tmp/release-images.json').write_text(json.dumps({'revision': sha, 'images': images}))


def deploy():
    validate()
    release = json.loads((ROOT / 'tmp/release-images.json').read_text())
    sha = release['revision']
    if not re.fullmatch('[0-9a-f]{40}', sha):
        raise ValueError('REVISION_INVALID')
    with tempfile.TemporaryDirectory(prefix='wl-deploy-') as directory:
        directory = Path(directory)
        def private(name, value, mode=0o600):
            path = directory / name
            path.write_text(value)
            path.chmod(mode)
            return path
        key = private('key', os.environ['OCI_SSH_KEY'].strip() + '\n')
        hosts = private('known_hosts', os.environ['OCI_KNOWN_HOSTS'].strip() + '\n')
        askpass = private('askpass', '#!/bin/sh\nprintf "%s\\n" "$OCI_SSH_PASSWORD"\n', 0o700)
        runtime = private('runtime.json', json.dumps(release | {
            'registryUser': os.environ['GITHUB_ACTOR'], 'registryToken': os.environ['GHCR_TOKEN'],
            'secrets': {key: os.environ[key] for key in ('ADMIN_USERNAME', 'ADMIN_PASSWORD', 'DISCORD_WEBHOOK_URL', 'KMA_API_KEY')}
        }))
        bundle = directory / 'release.tar.gz'
        with tarfile.open(bundle, 'w:gz') as archive:
            for name in ('compose.yml', 'compose.public.yml', 'apply.py'):
                archive.add(ROOT / 'deploy' / name, arcname=name)
            archive.add(runtime, arcname='runtime.json')
        bundle.chmod(0o600)
        env = os.environ | {'SSH_ASKPASS': str(askpass), 'SSH_ASKPASS_REQUIRE': 'force', 'DISPLAY': ':0'}
        options = ['-i', str(key), '-o', f'UserKnownHostsFile={hosts}', '-o', 'StrictHostKeyChecking=yes',
                   '-o', 'IdentitiesOnly=yes', '-o', 'NumberOfPasswordPrompts=1', '-o', 'ConnectTimeout=20',
                   '-o', 'ServerAliveInterval=30', '-o', 'ServerAliveCountMax=6']
        remote = os.environ['OCI_USER'] + '@' + os.environ['OCI_HOST']
        upload = '/tmp/waterleague-' + sha + '.tar.gz'
        try:
            run('scp', *options, str(bundle), remote + ':' + upload, env=env, stdin=subprocess.DEVNULL)
            with (ROOT / 'deploy/receive.py').open() as source:
                run('ssh', *options, remote, 'sudo -n python3 - ' + sha, env=env, stdin=source)
        finally:
            subprocess.run(['ssh', *options, remote, 'rm -f -- ' + upload], env=env,
                           stdin=subprocess.DEVNULL, timeout=30, check=False)


if __name__ == '__main__':
    try:
        {'validate': validate, 'build': build, 'deploy': deploy}[sys.argv[1]]()
    except ValueError as error:
        raise SystemExit(str(error)) from None
    except Exception:
        raise SystemExit('DEPLOY_COMMAND_FAILED') from None
