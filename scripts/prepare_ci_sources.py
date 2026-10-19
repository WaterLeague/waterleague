"""비밀값 없는 고정 공개 원문을 해시 검증 후 시험 경로에 복원."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import tarfile

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'simulation/tests/fixtures'


def prepare(root=ROOT):
    root = Path(root).resolve()
    manifest = json.loads((FIXTURES / 'public-sources-v1.json').read_text())
    archive = FIXTURES / 'public-sources-v1.tar.gz'
    if hashlib.sha256(archive.read_bytes()).hexdigest() != manifest['archiveSha256']:
        raise ValueError('CI_SOURCE_ARCHIVE_HASH_MISMATCH')
    expected = {row['path']: row for row in manifest['files']}
    pending = []
    with tarfile.open(archive, 'r:gz') as bundle:
        members = bundle.getmembers()
        if len(members) != len(expected) or {m.name for m in members} != set(expected):
            raise ValueError('CI_SOURCE_MEMBERS_MISMATCH')
        for member in members:
            name = PurePosixPath(member.name)
            if not member.isfile() or name.is_absolute() or '..' in name.parts:
                raise ValueError('CI_SOURCE_PATH_INVALID')
            row = expected[member.name]
            target = root / member.name
            if target.is_symlink() or target.resolve() != target or not target.is_relative_to(root):
                raise ValueError('CI_SOURCE_PATH_INVALID')
            if member.size != row['bytes'] or member.size > 16_000_000:
                raise ValueError('CI_SOURCE_SIZE_INVALID')
            raw = bundle.extractfile(member).read()
            if hashlib.sha256(raw).hexdigest() != row['sha256']:
                raise ValueError('CI_SOURCE_HASH_MISMATCH')
            if target.exists() and target.read_bytes() != raw:
                raise ValueError('CI_EXISTING_SOURCE_CHANGED')
            pending.append((target, raw))
    for target, raw in pending:
        if target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as stream:
            stream.write(raw)
    return len(pending)


if __name__ == '__main__':
    print(json.dumps({'verifiedPublicSources': prepare()}))
