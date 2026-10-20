"""소유 정보와 분리한 수치 산출물 캐시. 손상·잠금 실패 시 재계산."""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import shutil
import stat
import sys
import time
import uuid

from .engine import swmm
from . import placement_validation
from .spatial import suitability

SCHEMA = 1
MAX_ENTRY_BYTES = 64 * 1024 * 1024 - 1024 * 1024
FILES = frozenset(
    ['builder.py', 'model-source.json', 'model.json', 'placements.json', 'result.json']
    + [f'{label}.{suffix}' for label in ['baseline', 'strategy', 'low', 'high']
       for suffix in ['inp', 'rpt', 'out']]
)
RESULT_FIELDS = frozenset([
    'validationLevel', 'official', 'scoreRule', 'score', 'baseline', 'strategy',
    'sensitivity', 'assumptions', 'engine', 'reportPrecision',
])
MARKER = b'waterleague-result-cache-v1\n'

def execution_policy():
    # 수치 생성기의 고정 버전과 별개로 실행 허용 규칙을 캐시 식별자에 결속한다.
    return {
        'cacheSha256': digest(Path(__file__).read_bytes()),
        'runnerSha256': digest(Path(__file__).with_name('run_job.py').read_bytes()),
        'placementValidationSha256': digest(Path(placement_validation.__file__).read_bytes()),
        'siteSuitabilitySha256': digest(Path(suitability.__file__).read_bytes()),
        'siteSuitabilityPolicySha256': suitability.POLICY_SHA256,
    }


class CacheUnavailable(OSError):
    pass


class CacheInvalid(ValueError):
    pass


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(value).hexdigest()


def decoded(value):
    def invalid(_):
        raise CacheInvalid('비유한 JSON 값')
    def finite_number(text):
        number = float(text)
        if not math.isfinite(number):
            raise CacheInvalid('JSON 수치 범위 초과')
        return number
    def unique_fields(pairs):
        if len({key for key, _ in pairs}) != len(pairs):
            raise CacheInvalid('중복 JSON 필드')
        return dict(pairs)
    return json.loads(value, parse_constant=invalid, parse_float=finite_number, object_pairs_hook=unique_fields)


def computation_identity(model_source, request):
    if set(request) != {'modelHash', 'inputHash', 'placements'}:
        raise ValueError('계산 요청 필드 불일치')
    if any(not isinstance(request.get(name), str) or not re.fullmatch(r'[a-f0-9]{64}', request[name])
           for name in ['modelHash', 'inputHash']):
        raise ValueError('계산 요청 해시 오류')
    if digest(model_source) != request['modelHash']:
        raise ValueError('모델 원문 불일치')
    engine = {
        'version': '5.2.4', 'revision': swmm.REVISION,
        'binarySha256': digest(swmm.library_path().read_bytes()),
        'generatorSha256': digest(Path(swmm.__file__).read_bytes()),
        'platform': platform.platform(),
    }
    identity = {
        'schema': SCHEMA, 'modelHash': request['modelHash'], 'inputHash': request['inputHash'],
        'placementsSha256': digest(encoded(request['placements'])), 'engine': engine,
        'executionPolicySha256': digest(encoded(execution_policy())),
        'python': sys.version, 'machine': platform.machine(),
    }
    return digest(encoded(identity)), identity


def _read(path, limit=MAX_ENTRY_BYTES):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or
                info.st_nlink != 1 or info.st_mode & 0o077 or info.st_size > limit):
            raise CacheInvalid('파일 형식·권한·크기 오류')
        value = stream.read(limit + 1)
        if len(value) > limit:
            raise CacheInvalid('파일 크기 초과')
        return value


def _write(path, value):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(value)
        stream.flush()
        os.fsync(stream.fileno())


def _private_directory(path):
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise CacheUnavailable('비공개 캐시 디렉터리 필요')


def validate_files(files, identity):
    if set(files) != FILES or sum(map(len, files.values())) > MAX_ENTRY_BYTES:
        raise CacheInvalid('산출물 목록·크기 오류')
    if digest(files['model-source.json']) != identity['modelHash']:
        raise CacheInvalid('모델 원본 불일치')
    if digest(encoded(decoded(files['placements.json']))) != identity['placementsSha256']:
        raise CacheInvalid('배치 불일치')
    if digest(files['builder.py']) != identity['engine']['generatorSha256']:
        raise CacheInvalid('빌더 불일치')
    result = decoded(files['result.json'])
    model = decoded(files['model-source.json'])
    if (set(result) != RESULT_FIELDS or result['engine'] != identity['engine'] or
            result['validationLevel'] != 'EXPLORATORY' or result['official'] is not False or
            result['scoreRule'] != model['scoreRule'] or not math.isfinite(result['score'])):
        raise CacheInvalid('계산 결과 계약 불일치')
    return result


class ResultCache:
    files = FILES
    marker = MARKER
    validate = staticmethod(validate_files)

    def __init__(self, root, *, max_entries=128, max_bytes=2 * 1024 ** 3, ttl_seconds=7 * 86400):
        self.root = Path(root).absolute()
        self.max_entries = max_entries
        self.max_bytes = max_bytes
        self.ttl_seconds = ttl_seconds
        if min(max_entries, max_bytes, ttl_seconds) <= 0:
            raise ValueError('캐시 한도 오류')

    @contextmanager
    def _guard(self):
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        _private_directory(self.root)
        marker = self.root / '.waterleague-cache'
        if not marker.exists() and any(p.name != '.lock' for p in self.root.iterdir()):
            raise CacheUnavailable('전용 캐시 경로 필요')
        fd = os.open(self.root / '.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
        with os.fdopen(fd, 'rb+') as lock:
            info = os.fstat(lock.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1 or info.st_mode & 0o077:
                raise CacheUnavailable('캐시 잠금 파일 오류')
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                if not marker.exists():
                    _write(marker, self.marker)
                if _read(marker, 64) != self.marker:
                    raise CacheUnavailable('캐시 표식 불일치')
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def _remove(self, path):
        if path.is_symlink() or not path.is_dir():
            path.unlink(missing_ok=True)
        else:
            shutil.rmtree(path)

    def _prune(self):
        entries = []
        now = time.time()
        for path in self.root.iterdir():
            if re.fullmatch(r'\.pending-[a-f0-9]{32}', path.name):
                self._remove(path)
            elif re.fullmatch(r'[a-f0-9]{64}', path.name):
                try:
                    _private_directory(path)
                    age = now - path.stat().st_mtime
                    if age < -60 or age > self.ttl_seconds:
                        raise CacheInvalid('캐시 보관 기간 초과')
                    children = list(path.iterdir())
                    if {p.name for p in children} != self.files | {'cache.json'}:
                        raise CacheInvalid('캐시 목록 오류')
                    if any(not stat.S_ISREG(p.lstat().st_mode) for p in children):
                        raise CacheInvalid('캐시 파일 형식 오류')
                    size = sum(p.stat().st_size for p in children)
                    if size > MAX_ENTRY_BYTES + 65536:
                        raise CacheInvalid('캐시 크기 초과')
                    entries.append((path.stat().st_mtime, size, path))
                except (OSError, ValueError):
                    self._remove(path)
        entries.sort()
        total = sum(size for _, size, _ in entries)
        while len(entries) > self.max_entries or total > self.max_bytes:
            _, size, path = entries.pop(0)
            self._remove(path)
            total -= size

    def _load(self, key, identity):
        path = self.root / key
        _private_directory(path)
        metadata = decoded(_read(path / 'cache.json', 65536))
        if (set(metadata) != {'identity', 'files'} or metadata['identity'] != identity or
                set(metadata['files']) != self.files or {p.name for p in path.iterdir()} != self.files | {'cache.json'}):
            raise CacheInvalid('캐시 식별자·목록 불일치')
        files = {}
        total = 0
        for name in sorted(self.files):
            value = _read(path / name, MAX_ENTRY_BYTES - total)
            total += len(value)
            if digest(value) != metadata['files'][name]:
                raise CacheInvalid('캐시 내용 해시 불일치')
            files[name] = value
        self.validate(files, identity)
        return files

    def load(self, key, identity):
        if key != digest(encoded(identity)):
            raise ValueError('캐시 키 불일치')
        try:
            with self._guard():
                self._prune()
                try:
                    return self._load(key, identity)
                except (OSError, ValueError, TypeError, KeyError, RecursionError):
                    self._remove(self.root / key)
        except (OSError, ValueError, TypeError, KeyError, RecursionError):
            pass
        return None

    def store(self, key, identity, files):
        if key != digest(encoded(identity)):
            raise ValueError('캐시 키 불일치')
        temporary = None
        try:
            self.validate(files, identity)
            if sum(map(len, files.values())) + 65536 > self.max_bytes:
                return False
            with self._guard():
                self._prune()
                target = self.root / key
                if target.exists() or target.is_symlink():
                    try:
                        self._load(key, identity)
                        return True
                    except (OSError, ValueError, TypeError, KeyError, RecursionError):
                        self._remove(target)
                temporary = self.root / ('.pending-' + uuid.uuid4().hex)
                temporary.mkdir(mode=0o700)
                for name, value in files.items():
                    _write(temporary / name, value)
                _write(temporary / 'cache.json', encoded({'identity': identity, 'files': {name: digest(value) for name, value in files.items()}}))
                os.rename(temporary, target)
                temporary = None
                self._prune()
                return target.is_dir()
        except (OSError, ValueError, TypeError, KeyError, RecursionError):
            return False
        finally:
            if temporary is not None:
                shutil.rmtree(temporary, ignore_errors=True)


def execute(model_source, request, directory, cache_root=None):
    directory = Path(directory)
    model = decoded(model_source)
    if not model['simulationAvailable'] or model['validationLevel'] != 'EXPLORATORY':
        raise ValueError('MODEL_NOT_ELIGIBLE')
    key, identity = computation_identity(model_source, request)
    if identity['engine']['generatorSha256'] != model['generatorSha256']:
        raise ValueError('GENERATOR_MISMATCH')
    # 과거 캐시의 성공 여부와 관계없이 현재 배치·안전 조건을 먼저 검사한다.
    placement_validation.cost(model, request['placements'])
    cache = ResultCache(cache_root) if cache_root is not None else None
    files = cache.load(key, identity) if cache else None
    if files is not None:
        # 대상 작업의 request와 lease 경로는 유지하고 파일 내용을 별도 복사한다.
        for name, value in files.items():
            if name == 'model-source.json':
                if (directory / name).read_bytes() != value:
                    raise ValueError('MODEL_SOURCE_MISMATCH')
            else:
                _write(directory / name, value)
        result = decoded(files['result.json'])
        mode = 'REUSED'
    else:
        result = swmm.experiment(model, request['placements'], directory)
        if cache:
            try:
                files = {}
                total = 0
                for name in sorted(FILES):
                    value = _read(directory / name, MAX_ENTRY_BYTES - total)
                    total += len(value)
                    files[name] = value
                cache.store(key, identity, files)
            except (OSError, ValueError):
                # 캐시 보관 실패는 이미 완료한 수치 계산의 성공을 취소하지 않는다.
                pass
        mode = 'COMPUTED'
    result['execution'] = {'schema': SCHEMA, 'mode': mode, 'computationKey': key}
    (directory / 'result.json').write_bytes(encoded(result) + b'\n')
    manifest = {name: digest((directory / name).read_bytes()) for name in sorted(FILES | {'request.json'})}
    (directory / 'manifest.json').write_bytes(encoded(manifest) + b'\n')
    return result
