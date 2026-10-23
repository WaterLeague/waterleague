"""실행 내용·비밀 설정이 같은 웹 전용 배포의 서버 내부 검증."""
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import tempfile


def execution(image):
    return {name: image.get(name) for name in ('Architecture', 'Os', 'Variant', 'RootFS')} | {
        'Config': {key: value for key, value in image['Config'].items() if key != 'Labels'}}


def release_images(release):
    values = dict(line.split('=', 1) for line in (Path(release)/'release.env').read_text().splitlines())
    images = {name: values['WL_'+name.upper()+'_IMAGE'] for name in ('api', 'worker', 'web')}
    if any(not re.fullmatch(f'ghcr.io/waterleague/waterleague-{name}@sha256:[a-f0-9]{{64}}', value)
           for name, value in images.items()):
        raise ValueError('DEPLOY_PREVIOUS_IMAGE_INVALID')
    return images


def identity(release, images, values, key, inspect):
    payload = {
        'schema': 'EXECUTION_AND_SECRETS_V1',
        'services': {name: execution(inspect(images[name])) for name in ('api', 'worker')},
        'compose': {name: hashlib.sha256((Path(release)/name).read_bytes()).hexdigest()
                    for name in ('compose.yml', 'compose.public.yml')},
        'secrets': values,
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()
    return hmac.new(key, raw, hashlib.sha256).hexdigest()


def paths(base):
    directory = Path(base)/'state/secrets'
    if directory.resolve() != directory.absolute():
        raise ValueError('DEPLOY_IDENTITY_PATH_INVALID')
    key, stamp = directory/'deployment-identity.key', directory/'deployment-identity.hmac'
    for path in (key, stamp):
        if path.is_symlink():
            raise ValueError('DEPLOY_IDENTITY_LINK_REJECTED')
        if path.exists() and (not path.is_file() or path.stat().st_uid != os.getuid()
                              or path.stat().st_mode & 0o077):
            raise ValueError('DEPLOY_IDENTITY_PERMISSION_INVALID')
    return key, stamp


def matches(base, previous, release, images, values, inspect):
    key_path, stamp_path = paths(base)
    if not key_path.exists() or not stamp_path.exists():
        return False
    key, stamp = key_path.read_bytes(), stamp_path.read_text()
    if len(key) != 32 or not re.fullmatch('[a-f0-9]{64}', stamp):
        return False
    # 새 이미지와 현재 실행 이미지 양쪽을 확인해 오래된 확인 기록으로 생략하지 않는다.
    return all(hmac.compare_digest(stamp, identity(folder, references, values, key, inspect))
               for folder, references in ((release, images), (previous, release_images(previous))))


def remember(base, release, images, values, inspect):
    key_path, stamp_path = paths(base)
    def publish(path, raw):
        descriptor, name = tempfile.mkstemp(prefix='.deployment-identity-', dir=path.parent)
        try:
            with os.fdopen(descriptor, 'wb') as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, path)
        finally:
            Path(name).unlink(missing_ok=True)
    if not key_path.exists():
        publish(key_path, secrets.token_bytes(32))
    key = key_path.read_bytes()
    if len(key) != 32:
        raise ValueError('DEPLOY_IDENTITY_KEY_INVALID')
    publish(stamp_path, identity(release, images, values, key, inspect).encode())
