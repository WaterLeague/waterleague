from concurrent.futures import ThreadPoolExecutor
import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import test_native_play_catalog as fixtures
import package_native_play as packaging
import verify_native_play_runtime as runtime_verification
from waterleague_sim.spatial import play_bundle
from waterleague_sim.spatial.play_catalog import NativeCatalogError, NativePlayCatalog


class NativePlayBundleTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        fixture = fixtures.NativePlayCatalogTests()
        source_root, sites, objects, _ = fixture.inputs()
        self.addCleanup(fixture.doCleanups)
        self.summary = fixtures.catalog.build(sites, objects, source_root / 'play')
        self.bundle = self.root / 'bundle'
        self.manifest = packaging.package(source_root / 'play', self.summary, self.bundle)
        self.checksum = self.write_manifest()

    def write_manifest(self):
        raw = (json.dumps(self.manifest, sort_keys=True) + '\n').encode()
        (self.bundle / 'manifest.json').write_bytes(raw)
        return hashlib.sha256(raw).hexdigest()

    def test_concurrent_restore_preserves_exact_database_and_reuses_readonly_cache(self):
        directory = self.root / 'cache' / self.manifest['databaseSha256']
        directory.mkdir(mode=0o700, parents=True)
        (directory / 'play-interrupted.part').write_bytes(b'partial')
        (directory / 'notes.txt').write_bytes(b'keep')
        with ThreadPoolExecutor(2) as workers:
            paths = list(workers.map(lambda _: play_bundle.materialize(self.bundle, self.root / 'cache', self.checksum), range(2)))
        self.assertEqual(paths[0], paths[1])
        path = paths[0]
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), self.summary['playSha256'])
        self.assertEqual(path.stat().st_mode & 0o777, 0o400)
        previous = path.stat().st_ino
        play_bundle.materialize(self.bundle, self.root / 'cache', self.checksum)
        self.assertEqual(previous, path.stat().st_ino)
        reader = NativePlayCatalog(path, self.summary['playSha256'])
        self.assertEqual(len(reader.bounds([0, 0, 100, 100])), 3)
        self.assertEqual(list(path.parent.glob('*.part')), [])
        self.assertEqual((directory / 'notes.txt').read_bytes(), b'keep')

    def test_corruption_is_rejected_and_partial_file_is_removed(self):
        chunk = self.bundle / self.manifest['chunks'][0]['file']
        original = chunk.read_bytes()
        chunk.write_bytes(original[:-1] + bytes([original[-1] ^ 1]))
        with self.assertRaises(NativeCatalogError):
            play_bundle.materialize(self.bundle, self.root / 'cache', self.checksum)
        self.assertEqual(list((self.root / 'cache').rglob('*.part')), [])
        self.assertEqual(list((self.root / 'cache').rglob('play.sqlite')), [])
        chunk.write_bytes(original)
        path = play_bundle.materialize(self.bundle, self.root / 'cache', self.checksum)
        path.chmod(0o600)
        path.write_bytes(b'bad')
        with self.assertRaises(NativeCatalogError):
            play_bundle.materialize(self.bundle, self.root / 'cache', self.checksum)
        self.assertEqual(path.read_bytes(), b'bad')

    def test_manifest_traversal_size_and_oversized_decompression_are_rejected(self):
        original = json.loads(json.dumps(self.manifest))
        for change in ({'file': '../outside.gz'}, {'bytes': 0}, {'gzipBytes': 41 * 1024**2}):
            self.manifest = json.loads(json.dumps(original))
            self.manifest['chunks'][0].update(change)
            checksum = self.write_manifest()
            with self.assertRaises(NativeCatalogError):
                play_bundle.materialize(self.bundle, self.root / 'invalid-cache', checksum)
        self.assertFalse((self.root / 'invalid-cache').exists())
        self.manifest = json.loads(json.dumps(original))
        payload = gzip.compress(b'a' * 1024**2, mtime=0)
        chunk = self.manifest['chunks'][0]
        chunk.update(bytes=4096, gzipBytes=len(payload), gzipSha256=hashlib.sha256(payload).hexdigest())
        self.manifest['databaseBytes'] = 4096
        (self.bundle / chunk['file']).write_bytes(payload)
        checksum = self.write_manifest()
        with self.assertRaises(NativeCatalogError):
            play_bundle.materialize(self.bundle, self.root / 'limited-cache', checksum)
        self.assertEqual(list((self.root / 'limited-cache').rglob('play.sqlite')), [])

    def test_cache_symlinks_and_wrong_manifest_hash_cannot_replace_files(self):
        with self.assertRaises(NativeCatalogError):
            play_bundle.materialize(self.bundle, self.root / 'cache', '0' * 64)
        directory = self.root / 'cache' / self.manifest['databaseSha256']
        directory.mkdir(parents=True, mode=0o700)
        sentinel = self.root / 'sentinel'
        sentinel.write_bytes(b'unchanged')
        (directory / 'play.sqlite').symlink_to(sentinel)
        with self.assertRaises(NativeCatalogError):
            play_bundle.materialize(self.bundle, self.root / 'cache', self.checksum)
        self.assertEqual(sentinel.read_bytes(), b'unchanged')

    def test_published_bundle_binds_the_validated_database_without_private_inputs(self):
        manifest = play_bundle.read_manifest(play_bundle.BUNDLE, play_bundle.MANIFEST_SHA256)
        report = json.loads((fixtures.catalog.source.ROOT / 'data/manifests/seoul-native-parking-v1.json').read_text())
        self.assertEqual(manifest['databaseSha256'], report['playSha256'])
        self.assertEqual(manifest['databaseBytes'], report['playBytes'])
        self.assertEqual(manifest['recordCount'], report['counts']['records'])
        self.assertEqual(manifest['generatorSha256'], hashlib.sha256(Path(packaging.__file__).read_bytes()).hexdigest())
        self.assertEqual(len({c['file'] for c in manifest['chunks']}), len(manifest['chunks']))
        for chunk in manifest['chunks']:
            path = play_bundle.BUNDLE / chunk['file']
            self.assertEqual(path.stat().st_size, chunk['gzipBytes'])
            self.assertEqual(play_bundle.file_hash(path), chunk['gzipSha256'])

    def test_runtime_evidence_binds_both_current_readers_and_all_districts(self):
        root = fixtures.catalog.source.ROOT
        value = json.loads((root / 'data/benchmarks/native-play-runtime-v4.json').read_text())
        self.assertEqual(value['verifierSha256'], play_bundle.file_hash(Path(runtime_verification.__file__)))
        self.assertEqual(value['bundleSha256'], play_bundle.MANIFEST_SHA256)
        self.assertEqual(value['workerBundleReaderSha256'], play_bundle.file_hash(Path(play_bundle.__file__)))
        self.assertEqual(value['workerCatalogReaderSha256'], play_bundle.file_hash(root / 'simulation/waterleague_sim/spatial/play_catalog.py'))
        for filename, checksum in value['javaSources'].items():
            self.assertEqual(checksum, play_bundle.file_hash(root / filename))
        self.assertEqual(value['districtsCompared'], 25)
        self.assertGreater(value['apiWorkerCellsCompared'], 0)
        self.assertTrue(value['fullCellJsonMatched'])
        self.assertTrue(value['engineCasesVerified'])
        self.assertEqual(len(value['engineCases']), 6)
        self.assertFalse(value['privateOriginalsRequired'])
        self.assertFalse(value['gameRuntimeMigrated'])


if __name__ == '__main__':
    unittest.main()
