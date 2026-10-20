"""현재 관측 결속의 해시 고정 공개 원문 조회. 이전 공간 모델의 기상 결속 미사용."""
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import zipfile

from ..engine.swmm import ROOT
from ..spatial import game_catalog

DIRECTORY = ROOT / 'backend/src/main/resources/native-weather/v1'
MANIFEST_SHA256 = '53fbf7f805ba428ced5ddc00926260d5c157ffb7294860fba5dcf942a7927a7b'


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def identity(path):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode):
        raise ValueError('OBSERVED_SOURCE_ARCHIVE_INVALID')
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


@lru_cache(maxsize=1)
def _sources():
    if any(path.is_symlink() for path in (DIRECTORY, *DIRECTORY.parents)):
        raise ValueError('OBSERVED_SOURCE_ARCHIVE_INVALID')
    manifest_path = DIRECTORY / 'manifest.json'
    if not 1 <= identity(manifest_path)[2] <= 1024**2:
        raise ValueError('OBSERVED_SOURCE_ARCHIVE_INVALID')
    raw = manifest_path.read_bytes()
    manifest = json.loads(raw)
    if digest(raw) != MANIFEST_SHA256 or manifest['forcingCatalogSha256'] != game_catalog.SHA256:
        raise ValueError('OBSERVED_SOURCE_ARCHIVE_INVALID')
    path = DIRECTORY / 'sources.zip'
    before = identity(path)
    if manifest['archive']['file'] != 'sources.zip' or before[2] != manifest['archive']['bytes'] or before[2] > 64 * 1024**2:
        raise ValueError('OBSERVED_SOURCE_ARCHIVE_INVALID')
    stream = os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), 'rb')
    try:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != manifest['archive']['sha256'] or identity(path) != before:
            raise ValueError('OBSERVED_SOURCE_ARCHIVE_INVALID')
        stream.seek(0)
        archive = zipfile.ZipFile(stream)
        entries = {row['file']: row for row in manifest['files']}
        members = archive.infolist()
        if (not 1 <= len(entries) == len(members) <= 4096
                or set(entries) != {member.filename for member in members}
                or sum(row['bytes'] for row in entries.values()) > 512 * 1024**2):
            raise ValueError('OBSERVED_SOURCE_ARCHIVE_INVALID')
        for member in members:
            relative = PurePosixPath(member.filename)
            if (relative.is_absolute() or '..' in relative.parts or relative.as_posix() != member.filename
                    or member.is_dir() or member.flag_bits & 1 or member.compress_type != zipfile.ZIP_DEFLATED
                    or not 0 < member.file_size == entries[member.filename]['bytes'] <= 16 * 1024**2):
                raise ValueError('OBSERVED_SOURCE_ARCHIVE_INVALID')
        return archive, entries, before, path, stream, manifest
    except BaseException:
        stream.close()
        raise


def read_source(relative, expected):
    archive, entries, before, path, _, _ = _sources()
    row = entries.get(relative)
    if row is None or row['sha256'] != expected or identity(path) != before:
        raise ValueError('OBSERVED_SOURCE_REFERENCE_INVALID')
    with archive.open(relative) as source:
        body = source.read(row['bytes'] + 1)
    if len(body) != row['bytes'] or digest(body) != expected:
        raise ValueError('OBSERVED_SOURCE_HASH_MISMATCH')
    return body


def implementation_source(checksum):
    *_, manifest = _sources()
    return read_source(manifest['implementationFiles'][checksum], checksum)
