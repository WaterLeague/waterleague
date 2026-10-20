"""공개 조각의 제한 크기·해시 검증 후 불변 계산 DB를 원자적으로 복원."""
from contextlib import contextmanager
from functools import lru_cache
import fcntl
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import tempfile
import threading

from ..engine.swmm import ROOT
from .play_catalog import NativeCatalogError, NativePlayCatalog, file_hash

BUNDLE = ROOT / 'backend/src/main/resources/native-play/v1'
MANIFEST_SHA256 = '9cf8102058e282034d1f5f56d74c666e11703a9a6c3b83e94aee5be0a11d21dc'
CHUNK_BYTES = 32 * 1024**2
_process_lock = threading.RLock()


def read_manifest(bundle, expected_sha256):
    try:
        path = bundle / 'manifest.json'
        if path.is_symlink() or not 1 <= path.stat().st_size <= 128 * 1024:
            raise ValueError()
        raw = path.read_bytes()
        value = json.loads(raw)
        if (hashlib.sha256(raw).hexdigest() != expected_sha256 or value['schemaVersion'] != 1
                or value['id'] != 'SEOUL_NGII_REFERENCE_PLAY_V1' or value['coordinateSystem'] != 'EPSG:5186'
                or value['chunkBytes'] != CHUNK_BYTES or not re.fullmatch('[a-f0-9]{64}', value['databaseSha256'])
                or type(value['databaseBytes']) is not int or not 4096 <= value['databaseBytes'] <= 16 * 1024**3
                or not 1 <= len(value['chunks']) <= 512):
            raise ValueError()
        total = 0
        for index, chunk in enumerate(value['chunks']):
            if (chunk['file'] != f'part-{index:03}.sqlite.gz'
                    or any(type(chunk[key]) is not int for key in ('bytes', 'gzipBytes'))
                    or not 1 <= chunk['bytes'] <= CHUNK_BYTES or not 1 <= chunk['gzipBytes'] <= 40 * 1024**2
                    or (index < len(value['chunks']) - 1 and chunk['bytes'] != CHUNK_BYTES)
                    or any(not re.fullmatch('[a-f0-9]{64}', chunk[key]) for key in ('sha256', 'gzipSha256'))):
                raise ValueError()
            total += chunk['bytes']
        if total != value['databaseBytes']:
            raise ValueError()
        return value
    except (OSError, ValueError, TypeError, KeyError):
        raise NativeCatalogError('NATIVE_BUNDLE_INVALID') from None


@contextmanager
def exclusive_lock(path):
    with _process_lock:
        descriptor = os.open(path, os.O_CREAT | os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
        try:
            # Java FileChannel과 같은 POSIX 잠금으로 두 런타임의 동시 복원을 직렬화한다.
            fcntl.lockf(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            os.close(descriptor)


def materialize(bundle, cache, expected_sha256=MANIFEST_SHA256):
    bundle, cache = Path(bundle).resolve(), Path(cache).resolve()
    manifest = read_manifest(bundle, expected_sha256)
    directory = cache / manifest['databaseSha256']
    try:
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        if (directory.is_symlink() or directory.stat().st_uid != os.geteuid()
                or stat.S_IMODE(directory.stat().st_mode) & 0o077):
            raise ValueError()
        database = directory / 'play.sqlite'
        with exclusive_lock(directory / '.lock'):
            # 이전 프로세스가 중단된 뒤 남긴 자체 복원 파일만 잠금 안에서 정리한다.
            for pending in directory.glob('play-*.part'):
                if pending.is_symlink() or not pending.is_file():
                    raise ValueError()
                pending.unlink()
            if os.path.lexists(database):
                if (database.is_symlink() or not database.is_file() or database.stat().st_size != manifest['databaseBytes']
                        or file_hash(database) != manifest['databaseSha256']):
                    raise ValueError()
                return database
            descriptor, temporary = tempfile.mkstemp(prefix='play-', suffix='.part', dir=directory)
            temporary = Path(temporary)
            try:
                digest = hashlib.sha256()
                with os.fdopen(descriptor, 'wb') as target:
                    for chunk in manifest['chunks']:
                        path = bundle / chunk['file']
                        if path.is_symlink() or path.stat().st_size != chunk['gzipBytes']:
                            raise ValueError()
                        payload = path.read_bytes()
                        if hashlib.sha256(payload).hexdigest() != chunk['gzipSha256']:
                            raise ValueError()
                        with gzip.GzipFile(fileobj=io.BytesIO(payload)) as stream:
                            raw = stream.read(chunk['bytes'] + 1)
                        if len(raw) != chunk['bytes'] or hashlib.sha256(raw).hexdigest() != chunk['sha256']:
                            raise ValueError()
                        digest.update(raw)
                        target.write(raw)
                    if digest.hexdigest() != manifest['databaseSha256'] or target.tell() != manifest['databaseBytes']:
                        raise ValueError()
                    target.flush()
                    os.fsync(target.fileno())
                temporary.chmod(0o400)
                os.replace(temporary, database)
                return database
            finally:
                temporary.unlink(missing_ok=True)
    except (OSError, ValueError, TypeError, KeyError, EOFError):
        raise NativeCatalogError('NATIVE_BUNDLE_INVALID') from None


@lru_cache(maxsize=1)
def _open_catalog(bundle, cache, checksum):
    path = materialize(bundle, cache, checksum)
    manifest = read_manifest(bundle, checksum)
    return NativePlayCatalog(path, manifest['databaseSha256'])


def open_catalog():
    cache = Path(os.environ.get('NATIVE_SPATIAL_CACHE', ROOT / 'tmp/native-spatial')).absolute()
    return _open_catalog(BUNDLE, cache, MANIFEST_SHA256)
