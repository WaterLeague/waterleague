"""SSH로 받은 파일의 크기·형식을 확인하고 비공개 배포 디렉터리에서 실행."""
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import tempfile

revision = sys.argv[1]
if os.getuid() != 0 or not re.fullmatch('[0-9a-f]{40}', revision):
    raise SystemExit('DEPLOY_RECEIVER_INVALID')
os.umask(0o077)
bundle = Path('/tmp/waterleague-' + revision + '.tar.gz')
if bundle.is_symlink() or not bundle.is_file() or bundle.stat().st_size > 1024 * 1024:
    raise SystemExit('DEPLOY_BUNDLE_INVALID')
try:
    with tempfile.TemporaryDirectory(prefix='waterleague-release-') as directory:
        directory = Path(directory)
        with tarfile.open(bundle) as archive:
            members = archive.getmembers()
            names = {'compose.yml', 'compose.public.yml', 'apply.py', 'storage.py', 'runtime_identity.py', 'runtime.json'}
            if len(members) != len(names) or {m.name for m in members} != names:
                raise ValueError('DEPLOY_BUNDLE_FILES_INVALID')
            for member in members:
                if not member.isfile() or member.size > 256 * 1024:
                    raise ValueError('DEPLOY_BUNDLE_ENTRY_INVALID')
                (directory / member.name).write_bytes(archive.extractfile(member).read())
        subprocess.run(['python3', str(directory / 'apply.py'), revision], cwd=directory, check=True)
finally:
    bundle.unlink(missing_ok=True)
