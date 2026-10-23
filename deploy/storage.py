"""완료된 재현 파일의 내용 보존 중복 제거와 운영 백업 개수 관리."""
import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import gzip
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import subprocess
import time
import uuid

BACKUP_KEEP = 3
BACKUP_NAME = re.compile(r'\d{8}T\d{6}Z-[a-f0-9]{12}\.tar(?:\.gz)?\.age')
AGE_HEADER = b'age-encryption.org/v1\n'
MAX_FILE_BYTES = 64 * 1024**2
MAX_CACHE_ENTRIES = 500_000
COMPRESSIBLE = frozenset(('result.json', 'forcing.json', 'antecedent.json', 'model.json',
    'public-asset-policy.json', *(label+'.'+suffix for label in ('baseline', 'strategy', 'cistern_demand')
                               for suffix in ('inp', 'rpt', 'out'))))


def signature(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns,
            info.st_ctime_ns, info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode))


def regular(path):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode):
        raise ValueError('STORAGE_REGULAR_FILE_REQUIRED')
    return info


def prune_backups(base, keep=BACKUP_KEEP):
    if keep < 3:
        raise ValueError('STORAGE_BACKUP_MINIMUM_REQUIRED')
    root = Path(base) / 'backups'
    if root.is_symlink() or root.resolve() != root.absolute():
        raise ValueError('STORAGE_BACKUP_PATH_INVALID')
    files = sorted([*root.glob('*.tar.age'), *root.glob('*.tar.gz.age')])
    for path in files:
        if not BACKUP_NAME.fullmatch(path.name):
            raise ValueError('STORAGE_BACKUP_NAME_INVALID')
        regular(path)
    # 보존할 암호화 백업이 모두 존재하는 경우에만 오래된 백업을 정리한다.
    for path in files[-keep:]:
        with path.open('rb') as stream:
            if stream.read(len(AGE_HEADER)) != AGE_HEADER:
                raise ValueError('STORAGE_BACKUP_HEADER_INVALID')
    removed = files[:-keep]
    released = sum(path.stat().st_size for path in removed)
    for path in removed:
        path.unlink()
    return {'retainedBackups': min(keep, len(files)), 'removedBackups': len(removed),
            'releasedBackupBytes': released}


def completed_directories(base):
    # 실행 중·재시도 가능한 작업은 제외하고 게시가 끝난 원문만 공유한다.
    query = """BEGIN READ ONLY;
        SELECT coalesce(json_agg(row_to_json(t)), '[]'::json) FROM (
          SELECT 'shared-physics' AS kind,id,lease_token FROM shared_physics_jobs
          WHERE state='SUCCEEDED' AND finished_at<clock_timestamp()-interval '10 minutes'
          UNION ALL
          SELECT 'historical' AS kind,id,lease_token FROM historical_experiments
          WHERE state='SUCCEEDED' AND finished_at<clock_timestamp()-interval '10 minutes'
        ) t;
        COMMIT;"""
    result = subprocess.run(['docker', 'exec', '-i', 'waterleague-db-1', 'psql', '-X', '-qAt',
                             '-v', 'ON_ERROR_STOP=1', '-U', 'wl_admin', '-d', 'waterleague'],
                            input=query, text=True, capture_output=True, timeout=60, check=True)
    rows = json.loads(result.stdout)
    root = Path(base) / 'state/artifacts'
    directories = []
    for row in rows:
        if row['kind'] not in ('shared-physics', 'historical'):
            raise ValueError('STORAGE_JOB_KIND_INVALID')
        directory = root / row['kind'] / str(uuid.UUID(row['id'])) / str(uuid.UUID(row['lease_token']))
        if directory.exists():
            directories.append(directory)
    return sorted(directories)


def image_cleanup_plan(images, protected_revisions, container_images, protected_references=()):
    removable = []
    for image in images:
        labels = image.get('Config', {}).get('Labels') or {}
        revision = labels.get('org.opencontainers.image.revision', '')
        references = (image.get('RepoTags') or []) + (image.get('RepoDigests') or [])
        if (labels.get('org.opencontainers.image.source') != 'https://github.com/WaterLeague/waterleague'
                or not re.fullmatch('[a-f0-9]{40}', revision) or not references
                or any(not re.fullmatch(r'ghcr\.io/waterleague/waterleague-(api|worker|web)(?:@sha256:[a-f0-9]{64}|:[a-zA-Z0-9_.-]+)', ref)
                       for ref in references)
                or image['Id'] in container_images
                or any(ref in protected_references for ref in references)
                or any(revision.startswith(value) for value in protected_revisions)):
            continue
        removable.append(image['Id'])
    return removable


def prune_images(base, *, apply=False):
    base = Path(base)
    current = base/'current'
    revision = current.resolve().name
    if not current.is_symlink() or not re.fullmatch('[a-f0-9]{40}', revision):
        raise ValueError('STORAGE_CURRENT_RELEASE_INVALID')
    protected = {revision}
    for path in (base/'backups').iterdir():
        if BACKUP_NAME.fullmatch(path.name):
            protected.add(path.name[17:29])
    references = set()
    for directory in (base/'releases').iterdir():
        if re.fullmatch('[a-f0-9]{40}', directory.name) and any(directory.name.startswith(p) for p in protected):
            path = directory/'release.env'
            if directory.is_symlink() or directory.resolve() != directory.absolute():
                raise ValueError('STORAGE_RELEASE_PATH_INVALID')
            if regular(path).st_size > 65536:
                raise ValueError('STORAGE_RELEASE_METADATA_INVALID')
            for line in path.read_text().splitlines():
                if re.fullmatch(r'WL_(API|WORKER|WEB)_IMAGE=ghcr\.io/waterleague/waterleague-(api|worker|web)@sha256:[a-f0-9]{64}', line):
                    references.add(line.split('=', 1)[1])
    def docker(*args):
        return subprocess.run(['docker', *args], capture_output=True, text=True,
                              timeout=120, check=True).stdout
    identifiers = list(set(docker('image', 'ls', '--no-trunc', '--quiet', '--filter',
                                 'label=org.opencontainers.image.source=https://github.com/WaterLeague/waterleague').split()))
    images = json.loads(docker('image', 'inspect', *identifiers)) if identifiers else []
    containers = docker('ps', '--all', '--quiet').split()
    container_images = {item['Image'] for item in json.loads(docker('inspect', *containers))} if containers else set()
    removable = image_cleanup_plan(images, protected, container_images, references)
    removed = 0
    if apply:
        for identifier in removable:
            # 사용 중인 컨테이너를 보호하고 Docker의 참조 검사를 강제로 우회하지 않는다.
            result = subprocess.run(['docker', 'image', 'rm', '--no-prune', identifier],
                                    capture_output=True, timeout=120)
            removed += result.returncode == 0
    return {'retiredImageCandidates': len(removable), 'removedRetiredImages': removed}


def cold_directories(base):
    # 최신 연속 계산과 현재 게시된 주간·대회 점수의 원문은 항상 일반 파일로 유지한다.
    query = """BEGIN READ ONLY;
      SELECT coalesce(json_agg(row_to_json(t)), '[]'::json) FROM (
        SELECT j.id,j.lease_token,j.artifact_manifest_hash FROM shared_physics_jobs j
        WHERE j.state='SUCCEEDED' AND j.artifact_manifest_hash IS NOT NULL
          AND j.finished_at<clock_timestamp()-interval '1 hour'
          AND j.id<>(SELECT p.id FROM shared_physics_jobs p
            WHERE p.installation_id=j.installation_id AND p.state='SUCCEEDED'
            ORDER BY p.requested_through DESC,p.created_at DESC LIMIT 1)
          AND NOT EXISTS(SELECT 1 FROM shared_weekly_scores s WHERE s.source_job_id=j.id)
          AND NOT EXISTS(SELECT 1 FROM game_competition_live_scores s WHERE s.source_job_id=j.id)
      ) t;
      COMMIT;"""
    result = subprocess.run(['docker', 'exec', '-i', 'waterleague-db-1', 'psql', '-X', '-qAt',
        '-v', 'ON_ERROR_STOP=1', '-U', 'wl_admin', '-d', 'waterleague'],
        input=query, text=True, capture_output=True, timeout=60, check=True)
    return [(Path(base)/'state/artifacts/shared-physics'/str(uuid.UUID(row['id']))/str(uuid.UUID(row['lease_token'])),
             row['artifact_manifest_hash']) for row in json.loads(result.stdout)]


def compression_supported():
    result = subprocess.run(['docker', 'inspect', 'waterleague-api-1'],
                            capture_output=True, text=True, timeout=30, check=True)
    container = json.loads(result.stdout)[0]
    if container.get('State', {}).get('Health', {}).get('Status') != 'healthy':
        return False
    result = subprocess.run(['docker', 'image', 'inspect', container['Image']],
                            capture_output=True, text=True, timeout=30, check=True)
    labels = json.loads(result.stdout)[0].get('Config', {}).get('Labels') or {}
    return labels.get('io.waterleague.artifact-storage') == 'gzip-v1'


def compressed_digest(path, limit=MAX_FILE_BYTES):
    regular(path)
    digest = hashlib.sha256()
    length = 0
    with gzip.open(path, 'rb') as stream:
        while chunk := stream.read(min(1024*1024, limit+1-length)):
            length += len(chunk)
            if length > limit:
                raise ValueError('STORAGE_COMPRESSED_SIZE_INVALID')
            digest.update(chunk)
    return digest.hexdigest()


def compress_directory(directory, expected_manifest, *, owners=(0, 10001)):
    directory = Path(directory)
    if directory.resolve() != directory.absolute():
        raise ValueError('STORAGE_COLD_PATH_INVALID')
    if regular(directory/'manifest.json').st_size > 8*1024**2:
        raise ValueError('STORAGE_COLD_MANIFEST_INVALID')
    raw = (directory/'manifest.json').read_bytes()
    if len(raw) > 8*1024**2 or hashlib.sha256(raw).hexdigest() != expected_manifest:
        raise ValueError('STORAGE_COLD_MANIFEST_INVALID')
    manifest = json.loads(raw)
    if not isinstance(manifest, dict) or len(manifest) > 50_000:
        raise ValueError('STORAGE_COLD_MANIFEST_INVALID')
    marker_path = directory/'.storage-cold.json'
    marker = {}
    if marker_path.exists() or marker_path.is_symlink():
        info = regular(marker_path)
        if info.st_uid != os.getuid() or info.st_mode & 0o077 or info.st_size > 65536:
            raise ValueError('STORAGE_COLD_MARKER_INVALID')
        try:
            marker = json.loads(marker_path.read_bytes())
        except ValueError:
            marker = {}
    known = marker.get('files', {}) if isinstance(marker, dict) and marker.get('manifest') == expected_manifest else {}
    if not isinstance(known, dict):
        known = {}
    verified = {}
    count = 0
    for name in sorted(COMPRESSIBLE.intersection(manifest)):
        expected = manifest[name]
        if not isinstance(expected, str) or not re.fullmatch('[a-f0-9]{64}', expected):
            raise ValueError('STORAGE_COLD_HASH_INVALID')
        path = directory/name
        compressed = directory/(name+'.gz')
        if not path.exists():
            info = regular(compressed)
            fingerprint = list(signature(info))
            if (path.is_symlink() or (known.get(name) != fingerprint
                                      and compressed_digest(compressed) != expected)):
                raise ValueError('STORAGE_COLD_CONTENT_INVALID')
            verified[name] = fingerprint
            continue
        info = regular(path)
        if info.st_uid not in owners or info.st_mode & 0o022 or info.st_size > MAX_FILE_BYTES:
            raise ValueError('STORAGE_COLD_FILE_INVALID')
        if info.st_size < 4096:
            continue
        temporary = directory/('.storage-gzip-'+uuid.uuid4().hex)
        try:
            digest = hashlib.sha256()
            with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), 'rb') as source:
                with temporary.open('xb') as target:
                    with gzip.GzipFile(filename='', fileobj=target, mode='wb', compresslevel=1, mtime=0) as output:
                        while chunk := source.read(1024*1024):
                            digest.update(chunk)
                            output.write(chunk)
                    target.flush()
                    os.fsync(target.fileno())
            if digest.hexdigest() != expected or compressed_digest(temporary) != expected:
                raise ValueError('STORAGE_COLD_CONTENT_INVALID')
            if signature(regular(path)) != signature(info):
                raise ValueError('STORAGE_COLD_FILE_CHANGED')
            if temporary.stat().st_size >= info.st_size:
                continue
            if (temporary.stat().st_uid, temporary.stat().st_gid) != (info.st_uid, info.st_gid):
                os.chown(temporary, info.st_uid, info.st_gid)
            temporary.chmod(stat.S_IMODE(info.st_mode))
            if compressed.exists() or compressed.is_symlink():
                if compressed_digest(compressed) != expected:
                    raise ValueError('STORAGE_COLD_CONFLICT')
            else:
                # 완성·검증된 압축본만 게시하고 원문은 그 뒤에 제거한다.
                os.link(temporary, compressed, follow_symlinks=False)
            path.unlink()
            verified[name] = list(signature(regular(compressed)))
            count += 1
        finally:
            temporary.unlink(missing_ok=True)
    updated = {'manifest': expected_manifest, 'files': verified}
    if updated != marker and verified:
        temporary = directory/('.storage-marker-'+uuid.uuid4().hex)
        try:
            with temporary.open('xb') as target:
                target.write(json.dumps(updated, sort_keys=True).encode())
                target.flush()
                os.fsync(target.fileno())
            temporary.chmod(0o600)
            temporary.replace(marker_path)
        finally:
            temporary.unlink(missing_ok=True)
    return count


class Fingerprints:
    def __init__(self, directory):
        directory = Path(directory)
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        info = directory.lstat()
        if (directory.resolve() != directory.absolute() or not stat.S_ISDIR(info.st_mode)
                or info.st_uid != os.getuid() or info.st_mode & 0o077):
            raise ValueError('STORAGE_CACHE_DIRECTORY_INVALID')
        path = directory / 'fingerprints.sqlite3'
        if path.exists() or path.is_symlink():
            info = regular(path)
            if info.st_uid != os.getuid() or info.st_mode & 0o077:
                raise ValueError('STORAGE_CACHE_FILE_INVALID')
        self.db = sqlite3.connect(path)
        path.chmod(0o600)
        self.db.execute('PRAGMA cache_size=-8192')
        self.db.execute('PRAGMA journal_size_limit=8388608')
        self.db.execute('''CREATE TABLE IF NOT EXISTS fingerprints (
            device INTEGER, inode INTEGER, signature TEXT NOT NULL, sha256 TEXT NOT NULL,
            seen INTEGER NOT NULL, PRIMARY KEY(device,inode))''')
        self.writes = 0
        self.memo = {}

    def remember(self, info, sha):
        key, value = (info.st_dev, info.st_ino), (signature(info), sha)
        if self.memo.get(key) == value:
            return
        if len(self.memo) >= 100_000:
            self.memo.clear()
        self.memo[key] = value
        self.db.execute('INSERT OR REPLACE INTO fingerprints VALUES(?,?,?,?,?)',
                        (info.st_dev, info.st_ino, json.dumps(signature(info)), sha, int(time.time())))
        self.writes += 1
        if self.writes % 512 == 0:
            self.db.commit()

    def digest(self, path, info=None):
        info = regular(path) if info is None else info
        memory = self.memo.get((info.st_dev, info.st_ino))
        if memory and memory[0] == signature(info):
            return memory[1], info
        flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
        with os.fdopen(os.open(path, flags), 'rb') as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_FILE_BYTES:
                raise ValueError('STORAGE_FILE_TYPE_OR_SIZE_INVALID')
            memory = self.memo.get((before.st_dev, before.st_ino))
            cached = None if memory else self.db.execute(
                'SELECT signature,sha256 FROM fingerprints WHERE device=? AND inode=?',
                (before.st_dev, before.st_ino)).fetchone()
            if memory and memory[0] == signature(before):
                sha = memory[1]
            elif cached and cached[0] == json.dumps(signature(before)):
                sha = cached[1]
            else:
                sha = hashlib.file_digest(stream, 'sha256').hexdigest()
            after = os.fstat(stream.fileno())
            if signature(before) != signature(after):
                raise ValueError('STORAGE_FILE_CHANGED')
        self.remember(after, sha)
        return sha, after

    def close(self):
        self.db.execute('DELETE FROM fingerprints WHERE seen<?', (int(time.time()) - 7*86400,))
        count = self.db.execute('SELECT count(*) FROM fingerprints').fetchone()[0]
        if count > MAX_CACHE_ENTRIES:
            self.db.execute('DELETE FROM fingerprints WHERE rowid IN '
                            '(SELECT rowid FROM fingerprints ORDER BY seen LIMIT ?)',
                            (count-MAX_CACHE_ENTRIES,))
        self.db.commit()
        self.db.close()


def files_in(root, directory):
    relative = directory.relative_to(root)
    if (len(relative.parts) != 3 or relative.parts[0] not in ('shared-physics', 'historical')
            or directory.resolve() != directory.absolute()):
        raise ValueError('STORAGE_ARTIFACT_PATH_INVALID')
    for value in relative.parts[1:]:
        if str(uuid.UUID(value)) != value:
            raise ValueError('STORAGE_ARTIFACT_PATH_INVALID')
    for parent, names, files in os.walk(directory, followlinks=False):
        names.sort()
        for name in names:
            if not stat.S_ISDIR((Path(parent) / name).lstat().st_mode):
                raise ValueError('STORAGE_DIRECTORY_LINK_REJECTED')
        for name in sorted(files):
            path = Path(parent) / name
            regular(path)
            yield path


def same_bytes(first, second):
    with os.fdopen(os.open(first, os.O_RDONLY | os.O_NOFOLLOW), 'rb') as left:
        with os.fdopen(os.open(second, os.O_RDONLY | os.O_NOFOLLOW), 'rb') as right:
            while True:
                chunk = left.read(1024*1024)
                if chunk != right.read(1024*1024):
                    return False
                if not chunk:
                    return True


def share_file(original, target, sha, info, cache):
    if signature(regular(target)) != signature(info):
        raise ValueError('STORAGE_TARGET_CHANGED')
    prior_sha, prior = cache.digest(original)
    if prior_sha != sha or (prior.st_dev, prior.st_uid, prior.st_gid, stat.S_IMODE(prior.st_mode)) != (
            info.st_dev, info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)):
        raise ValueError('STORAGE_CANONICAL_CHANGED')
    temporary = target.with_name('.storage-link-' + uuid.uuid4().hex)
    try:
        os.link(original, temporary, follow_symlinks=False)
        # 해시뿐 아니라 실제 바이트·메타데이터를 대조한 뒤 한 경로씩 원자적으로 교체한다.
        if not stat.S_ISREG(temporary.lstat().st_mode) or not same_bytes(temporary, target):
            raise ValueError('STORAGE_CONTENT_MISMATCH')
        if signature(regular(target)) != signature(info):
            raise ValueError('STORAGE_TARGET_CHANGED')
        os.replace(temporary, target)
        cache.remember(regular(target), sha)
    finally:
        temporary.unlink(missing_ok=True)


def compact(base, directories, *, apply=False, owners=(0, 10001), progress=None):
    base = Path(base)
    root = base / 'state/artifacts'
    if root.resolve() != root.absolute():
        raise ValueError('STORAGE_ROOT_LINK_REJECTED')
    cache = Fingerprints(base / 'state/cache/artifact-storage')
    objects = {}
    duplicate_inodes = set()
    result = {'completedJobs': 0, 'files': 0, 'linkedFiles': 0, 'duplicatePhysicalBytes': 0}
    before_tree = hashlib.sha256()
    after_tree = hashlib.sha256()
    try:
        for directory in directories:
            for path in files_in(root, Path(directory)):
                info = regular(path)
                if info.st_uid not in owners or info.st_mode & 0o022:
                    raise ValueError('STORAGE_ARTIFACT_OWNER_OR_MODE_INVALID')
                if info.st_size > MAX_FILE_BYTES:
                    raise ValueError('STORAGE_ARTIFACT_TOO_LARGE')
                sha, info = cache.digest(path, info=info)
                record = str(path.relative_to(root)).encode() + b'\0' + sha.encode() + b'\n'
                before_tree.update(record)
                key = (sha, info.st_size, info.st_dev, info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode))
                canonical, canonical_device, canonical_inode = objects.setdefault(
                    key, (path, info.st_dev, info.st_ino))
                changed = False
                if (info.st_dev, info.st_ino) != (canonical_device, canonical_inode):
                    inode = (info.st_dev, info.st_ino)
                    if inode not in duplicate_inodes:
                        duplicate_inodes.add(inode)
                        if info.st_nlink == 1:
                            result['duplicatePhysicalBytes'] += info.st_blocks*512
                    if apply:
                        share_file(canonical, path, sha, info, cache)
                        result['linkedFiles'] += 1
                        changed = True
                verified = cache.digest(path)[0] if changed else sha
                if verified != sha:
                    raise ValueError('STORAGE_CONTENT_CHANGED')
                after_tree.update(str(path.relative_to(root)).encode() + b'\0' + verified.encode() + b'\n')
                result['files'] += 1
            result['completedJobs'] += 1
            if progress and result['completedJobs'] % 100 == 0:
                progress(result)
        result['beforeSha256'] = before_tree.hexdigest()
        result['afterSha256'] = after_tree.hexdigest()
        if result['beforeSha256'] != result['afterSha256']:
            raise ValueError('STORAGE_TREE_CHANGED')
        return result
    finally:
        cache.close()


@contextmanager
def guard(base):
    path = Path(base) / 'deploy.lock'
    if path.is_symlink():
        raise ValueError('STORAGE_LOCK_LINK_REJECTED')
    with path.open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def install(base):
    base = Path(base)
    target = base / 'maintenance'
    target.mkdir(mode=0o700, exist_ok=True)
    if target.resolve() != target.absolute() or target.stat().st_uid != 0:
        raise ValueError('STORAGE_INSTALL_PATH_INVALID')
    source = Path(__file__).read_bytes()
    script = target / 'storage.py'
    pending = target / '.storage.py.next'
    with pending.open('xb') as stream:
        stream.write(source)
    pending.chmod(0o600)
    pending.replace(script)
    unit = '''[Unit]
Description=Waterleague immutable artifact storage maintenance
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 /opt/waterleague/maintenance/storage.py maintain
Environment=DOCKER_CONFIG=/run/waterleague-storage
RuntimeDirectory=waterleague-storage
RuntimeDirectoryMode=0700
UMask=0077
Nice=15
IOSchedulingClass=idle
CPUQuota=50%
MemoryMax=512M
TimeoutStartSec=3600
NoNewPrivileges=yes
PrivateTmp=yes
PrivateDevices=yes
ProtectHome=yes
ProtectSystem=strict
ReadWritePaths=/opt/waterleague/state/artifacts /opt/waterleague/state/cache/artifact-storage /opt/waterleague/backups /opt/waterleague/deploy.lock
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
RestrictAddressFamilies=AF_UNIX
RestrictSUIDSGID=yes
LockPersonality=yes
'''
    timer = '''[Unit]
Description=Waterleague hourly storage maintenance

[Timer]
OnCalendar=hourly
Persistent=true
RandomizedDelaySec=300
Unit=waterleague-storage.service

[Install]
WantedBy=timers.target
'''
    Fingerprints(base / 'state/cache/artifact-storage').close()
    for name, content in [('waterleague-storage.service', unit), ('waterleague-storage.timer', timer)]:
        path = Path('/etc/systemd/system') / name
        if path.is_symlink():
            raise ValueError('STORAGE_UNIT_LINK_REJECTED')
        path.write_text(content)
        path.chmod(0o644)
    subprocess.run(['systemctl', 'daemon-reload'], check=True)
    subprocess.run(['systemctl', 'enable', '--now', 'waterleague-storage.timer'], check=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=('audit', 'maintain', 'install'))
    parser.add_argument('--base', type=Path, default=Path('/opt/waterleague'))
    args = parser.parse_args()
    if os.getuid() != 0 or args.base != Path('/opt/waterleague'):
        raise ValueError('STORAGE_HOST_IDENTITY_INVALID')
    os.umask(0o077)
    with guard(args.base):
        if args.mode == 'install':
            install(args.base)
            print('STORAGE_TIMER_INSTALLED', flush=True)
            return
        result = prune_backups(args.base) if args.mode == 'maintain' else {}
        result.update(prune_images(args.base, apply=args.mode == 'maintain'))
        if args.mode == 'maintain' and compression_supported():
            result['compressedFiles'] = 0
            for index, (directory, manifest) in enumerate(cold_directories(args.base)):
                result['compressedFiles'] += compress_directory(directory, manifest)
                if index % 100 == 0:
                    print(json.dumps({'compressedJobs': index+1, **result}), flush=True)
        result.update(compact(args.base, completed_directories(args.base), apply=args.mode == 'maintain',
                              progress=lambda value: print(json.dumps(value), flush=True)))
        print(json.dumps(result), flush=True)


if __name__ == '__main__':
    try:
        main()
    except BlockingIOError:
        print('STORAGE_SKIPPED_DEPLOYMENT_ACTIVE', flush=True)
    except Exception:
        raise SystemExit('STORAGE_MAINTENANCE_FAILED') from None
