"""내용 해시별 관측 원문의 불변 보관과 계산별 파일 연결."""
import errno
import fcntl
import hashlib
import os
import re
import uuid
from pathlib import Path

MAX_BYTES = 4_000_000


def read(path, expected=None):
    path = Path(path)
    if path.is_symlink() or path.resolve() != path.absolute() or not path.is_file():
        raise ValueError('LIVE_PREVIOUS_SOURCE_INVALID')
    with path.open('rb') as stream:
        raw = stream.read(MAX_BYTES+1)
    if len(raw) > MAX_BYTES or (expected is not None and hashlib.sha256(raw).hexdigest() != expected):
        raise ValueError('LIVE_PREVIOUS_SOURCE_INVALID')
    return raw


def link(original, target, expected=None):
    original, target = Path(original), Path(target)
    raw = read(original, expected)
    try:
        os.link(original, target, follow_symlinks=False)
    except FileExistsError:
        if read(target) != raw:
            raise ValueError('LIVE_SOURCE_ARCHIVE_CONFLICT') from None
    except OSError as error:
        if error.errno not in (errno.EXDEV, errno.EOPNOTSUPP, errno.EPERM):
            raise
        # 하드 링크를 지원하지 않는 저장소에서도 같은 검증된 원문을 보존한다.
        with target.open('xb') as stream:
            stream.write(raw)
        target.chmod(0o400)


def store(root, target, raw, sha):
    if (not re.fullmatch('[a-f0-9]{64}', sha) or len(raw) > MAX_BYTES
            or hashlib.sha256(raw).hexdigest() != sha):
        raise ValueError('LIVE_SOURCE_HASH_INVALID')
    directory = Path(root).resolve()/'observation-sources'
    directory.mkdir(exist_ok=True)
    if directory.resolve() != directory.absolute():
        raise ValueError('LIVE_SOURCE_ARCHIVE_INVALID')
    source = directory/(sha+'.txt')
    if not source.exists():
        temporary = directory/('.'+uuid.uuid4().hex)
        try:
            with temporary.open('xb') as stream:
                stream.write(raw)
            temporary.chmod(0o400)
            # 완성된 파일만 게시하며 동시에 수집된 같은 원문을 덮어쓰지 않는다.
            try:
                os.link(temporary, source, follow_symlinks=False)
            except FileExistsError:
                pass
            except OSError as error:
                if error.errno not in (errno.EXDEV, errno.EOPNOTSUPP, errno.EPERM):
                    raise
                with (directory/('.'+sha+'.lock')).open('a+b') as lock:
                    fcntl.flock(lock.fileno(),fcntl.LOCK_EX)
                    if source.exists():
                        read(source,sha)
                    else:
                        os.rename(temporary,source)
        finally:
            temporary.unlink(missing_ok=True)
    link(source, target, sha)
