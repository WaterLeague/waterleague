"""재현 내용·복원 가능성·경합 중 원자적 교체와 보관 한도 검증."""
import hashlib
import gzip
import importlib.util
import json
import os
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import uuid

SPEC = importlib.util.spec_from_file_location('storage', Path(__file__).parents[1]/'storage.py')
storage = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(storage)


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        self.root = self.base/'state/artifacts'
        self.root.mkdir(parents=True)

    def job(self):
        directory = self.root/'shared-physics'/str(uuid.uuid4())/str(uuid.uuid4())
        directory.mkdir(parents=True)
        return directory

    def write(self, path, data, mode=0o600):
        path.write_bytes(data)
        path.chmod(mode)
        return path

    def backups(self, count):
        root = self.base/'backups'
        root.mkdir()
        return [self.write(root/f'20261023T{hour:02d}0000Z-012345abcdef.tar{suffix}.age',
                           storage.AGE_HEADER + b'encrypted fixture')
                for hour, suffix in zip(range(count), ['.gz', '']*count)]

    def compact(self, directories, apply=True):
        return storage.compact(self.base, directories, apply=apply, owners=(os.getuid(),))

    def test_mixed_backup_formats_keep_newest_three_and_ignore_partial(self):
        files = self.backups(7)
        partial = self.write(self.base/'backups/unfinished.tar.gz.age.partial', b'unfinished')
        result = storage.prune_backups(self.base)
        self.assertEqual(result['removedBackups'], 4)
        self.assertTrue(all(not p.exists() for p in files[:-3]))
        self.assertTrue(all(p.exists() for p in files[-3:]))
        self.assertTrue(partial.exists())
        self.assertEqual(storage.prune_backups(self.base)['removedBackups'], 0)

    def test_corrupt_retained_backup_prevents_any_deletion(self):
        files = self.backups(7)
        files[-1].write_bytes(b'incomplete')
        with self.assertRaisesRegex(ValueError, 'HEADER_INVALID'):
            storage.prune_backups(self.base)
        self.assertTrue(all(p.exists() for p in files))

    def test_backup_symlink_and_reduced_minimum_are_rejected(self):
        files = self.backups(4)
        files[0].unlink()
        files[0].symlink_to(files[-1])
        with self.assertRaises(ValueError):
            storage.prune_backups(self.base)
        with self.assertRaises(ValueError):
            storage.prune_backups(self.base, keep=2)
        self.assertTrue(files[1].exists())

    def test_complete_files_preserve_manifests_paths_and_open_readers(self):
        jobs = [self.job(), self.job()]
        for index, directory in enumerate(jobs):
            self.write(directory/'forcing.json', b'{"rain":0}\n'*800)
            self.write(directory/'request.json', str(index).encode())
            manifest = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.iterdir()}
            self.write(directory/'manifest.json', json.dumps(manifest).encode())
        with (jobs[1]/'forcing.json').open('rb') as reader:
            result = self.compact(jobs)
            self.assertEqual(reader.read(), (jobs[0]/'forcing.json').read_bytes())
        self.assertEqual(result['beforeSha256'], result['afterSha256'])
        self.assertEqual((jobs[0]/'forcing.json').stat().st_ino, (jobs[1]/'forcing.json').stat().st_ino)
        for directory in jobs:
            for name, sha in json.loads((directory/'manifest.json').read_bytes()).items():
                self.assertEqual(hashlib.sha256((directory/name).read_bytes()).hexdigest(), sha)
        self.assertEqual(self.compact(jobs)['linkedFiles'], 0)

    def test_archive_restores_shared_files_without_content_loss(self):
        jobs = [self.job(), self.job()]
        for directory in jobs:
            self.write(directory/'result.json', b'{"score":-0.00001}\n'*100)
        self.compact(jobs)
        archive = self.base/'backup.tar.gz'
        with tarfile.open(archive, 'w:gz') as target:
            target.add(self.root, arcname='artifacts')
        restored = self.base/'restored'
        with tarfile.open(archive) as target:
            self.assertTrue(any(entry.islnk() for entry in target.getmembers()))
            target.extractall(restored, filter='data')
        for directory in jobs:
            self.assertEqual((restored/'artifacts'/directory.relative_to(self.root)/'result.json').read_bytes(),
                             (directory/'result.json').read_bytes())

    def test_audit_does_not_replace_files_and_permissions_do_not_cross(self):
        jobs = [self.job(), self.job(), self.job()]
        paths = [self.write(d/'result.json', b'same'*400, mode)
                 for d, mode in zip(jobs, [0o600, 0o600, 0o400])]
        before = [p.stat().st_ino for p in paths]
        self.compact(jobs, apply=False)
        self.assertEqual(before, [p.stat().st_ino for p in paths])
        self.compact(jobs)
        self.assertEqual(paths[0].stat().st_ino, paths[1].stat().st_ino)
        self.assertNotEqual(paths[0].stat().st_ino, paths[2].stat().st_ino)
        self.assertEqual(paths[2].stat().st_mode & 0o777, 0o400)

    def test_interrupted_publication_keeps_original_and_removes_temporary(self):
        jobs = [self.job(), self.job()]
        for directory in jobs:
            self.write(directory/'result.json', b'same'*400)
        original = (jobs[1]/'result.json').stat().st_ino
        with patch.object(storage.os, 'replace', side_effect=OSError('interrupted')):
            with self.assertRaises(OSError):
                self.compact(jobs)
        self.assertEqual(original, (jobs[1]/'result.json').stat().st_ino)
        self.assertEqual(list(self.root.rglob('.storage-link-*')), [])

    def test_hash_collision_is_blocked_by_byte_comparison(self):
        jobs = [self.job(), self.job()]
        self.write(jobs[0]/'result.json', b'AAAA')
        self.write(jobs[1]/'result.json', b'BBBB')
        def colliding(_, path, info=None):
            return '0'*64, path.stat()
        with patch.object(storage.Fingerprints, 'digest', colliding):
            with self.assertRaisesRegex(ValueError, 'CONTENT_MISMATCH'):
                self.compact(jobs)
        self.assertEqual((jobs[1]/'result.json').read_bytes(), b'BBBB')

    def test_cache_invalidates_changes_with_preserved_length_and_mtime(self):
        directory = self.job()
        path = self.write(directory/'forcing.json', b'AAAA')
        cache = storage.Fingerprints(self.base/'state/cache/artifact-storage')
        self.addCleanup(cache.close)
        original, info = cache.digest(path)
        path.write_bytes(b'BBBB')
        os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns))
        changed, _ = cache.digest(path)
        self.assertNotEqual(original, changed)

    def test_symlinks_unsafe_permissions_and_unselected_jobs_are_not_shared(self):
        first, other = self.job(), self.job()
        self.write(first/'result.json', b'same')
        untouched = self.write(other/'result.json', b'same')
        inode = untouched.stat().st_ino
        self.compact([first])
        self.assertEqual(untouched.stat().st_ino, inode)
        (first/'external.json').symlink_to(untouched)
        with self.assertRaises(ValueError):
            self.compact([first])
        (first/'external.json').unlink()
        self.write(first/'unsafe.json', b'unsafe', 0o666)
        with self.assertRaises(ValueError):
            self.compact([first])

    def test_deployment_lock_excludes_maintenance(self):
        with storage.guard(self.base):
            with self.assertRaises(BlockingIOError):
                with storage.guard(self.base):
                    self.fail('concurrent maintenance')

    def test_image_plan_preserves_current_backup_container_and_foreign_images(self):
        def image(identifier, revision, repository='ghcr.io/waterleague/waterleague-worker'):
            return {'Id': identifier, 'Config': {'Labels': {
                'org.opencontainers.image.source': 'https://github.com/WaterLeague/waterleague',
                'org.opencontainers.image.revision': revision}}, 'RepoTags': [repository+':'+revision]}
        images = [image('current', '1'*40), image('backup', '2'*40), image('running', '3'*40),
                  image('retired', '4'*40), image('foreign', '5'*40, 'other/repository')]
        self.assertEqual(storage.image_cleanup_plan(images, {'1'*40, '2'*12}, {'running'}), ['retired'])

    def cold_job(self):
        directory = self.job()
        raw = b'{"score":-0.000000001}\n'*500
        path = self.write(directory/'result.json', raw)
        manifest = json.dumps({'result.json': hashlib.sha256(raw).hexdigest()}).encode()
        self.write(directory/'manifest.json', manifest)
        return directory, path, raw, hashlib.sha256(manifest).hexdigest()

    def test_retained_release_reused_image_digest_is_protected(self):
        reference = 'ghcr.io/waterleague/waterleague-api@sha256:'+'a'*64
        image = {'Id': 'older-api', 'Config': {'Labels': {
            'org.opencontainers.image.source': 'https://github.com/WaterLeague/waterleague',
            'org.opencontainers.image.revision': 'b'*40}}, 'RepoDigests': [reference]}
        self.assertEqual(storage.image_cleanup_plan([image], {'c'*40}, set(), {reference}), [])
        self.assertEqual(storage.image_cleanup_plan([image], {'c'*40}, set()), ['older-api'])

    def test_cold_compression_preserves_hash_and_is_resumable(self):
        directory, path, raw, manifest = self.cold_job()
        self.assertEqual(storage.compress_directory(directory, manifest, owners=(os.getuid(),)), 1)
        self.assertFalse(path.exists())
        self.assertEqual(gzip.decompress((directory/'result.json.gz').read_bytes()), raw)
        self.assertEqual(storage.compress_directory(directory, manifest, owners=(os.getuid(),)), 0)
        self.assertEqual(storage.compressed_digest(directory/'result.json.gz'), hashlib.sha256(raw).hexdigest())

    def test_cold_corruption_preserves_plain_original_and_rejects_bad_archive(self):
        directory, path, raw, manifest = self.cold_job()
        with patch.object(storage.os, 'link', side_effect=OSError('interrupted')):
            with self.assertRaises(OSError):
                storage.compress_directory(directory, manifest, owners=(os.getuid(),))
        self.assertEqual(path.read_bytes(), raw)
        self.assertEqual(list(directory.glob('.storage-gzip-*')), [])
        storage.compress_directory(directory, manifest, owners=(os.getuid(),))
        (directory/'result.json.gz').write_bytes(gzip.compress(b'corrupt'))
        with self.assertRaises(ValueError):
            storage.compress_directory(directory, manifest, owners=(os.getuid(),))


if __name__ == '__main__':
    unittest.main()
