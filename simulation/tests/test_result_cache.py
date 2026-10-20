"""동일 조건 분리·캐시 파일 보안·원자적 게시·실제 엔진 재사용 검사."""
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from waterleague_sim import result_cache as cache
from waterleague_sim.engine import swmm


def fixture(index=0):
    placements = [{'cellId': 'TEST', 'facilityType': 'RAIN_GARDEN', 'areaM2': 10}]
    model = cache.encoded({'id': 'SYNTHETIC_TEST_ONLY-' + str(index), 'scoreRule': 'TEST_ONLY'})
    builder = b'SYNTHETIC_TEST_ONLY_BUILDER'
    engine = {'version': 'TEST_ONLY', 'generatorSha256': cache.digest(builder)}
    identity = {'schema': 1, 'modelHash': cache.digest(model), 'inputHash': 'a' * 64,
                'placementsSha256': cache.digest(cache.encoded(placements)), 'engine': engine}
    result = dict.fromkeys(cache.RESULT_FIELDS, {})
    result.update(validationLevel='EXPLORATORY', official=False, score=1.0, scoreRule='TEST_ONLY', engine=engine)
    files = dict.fromkeys(cache.FILES, b'SYNTHETIC_TEST_ONLY')
    files.update({'builder.py': builder, 'model-source.json': model, 'placements.json': cache.encoded(placements),
                  'result.json': cache.encoded(result)})
    return cache.digest(cache.encoded(identity)), identity, files


def publish(root, key, identity, files, barrier, output):
    barrier.wait(timeout=10)
    output.put(cache.ResultCache(root).store(key, identity, files))


class ResultCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'cache'
        self.cache = cache.ResultCache(self.root)
        self.key, self.identity, self.files = fixture()

    def test_store_load_permissions_and_no_request_or_owner(self):
        self.assertTrue(self.cache.store(self.key, self.identity, self.files))
        self.assertEqual(self.cache.load(self.key, self.identity), self.files)
        self.assertEqual(self.root.stat().st_mode & 0o777, 0o700)
        for path in (self.root / self.key).iterdir():
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertNotIn('request.json', {p.name for p in (self.root / self.key).iterdir()})
        result = cache.decoded(self.files['result.json']) | {'ownerId': 'NOT_ALLOWED'}
        self.assertFalse(self.cache.store(self.key, self.identity, self.files | {'result.json': cache.encoded(result)}))

    def test_corrupt_missing_extra_and_nonfinite_artifacts_are_misses(self):
        for change in ['bytes', 'missing', 'extra', 'nonfinite', 'overflow', 'duplicate']:
            with self.subTest(change=change):
                self.assertTrue(self.cache.store(self.key, self.identity, self.files))
                entry = self.root / self.key
                if change == 'bytes':
                    (entry / 'strategy.out').write_bytes(b'CORRUPTED')
                elif change == 'missing':
                    (entry / 'strategy.out').unlink()
                elif change == 'extra':
                    (entry / 'request.json').write_text('{}')
                else:
                    value = self.files['result.json'].replace(b'"score":1.0', b'"score":NaN') if change == 'nonfinite' else (
                        self.files['result.json'].replace(b'"baseline":{}', b'"baseline":{"runoffM3":1e999}') if change == 'overflow' else
                        self.files['result.json'].replace(b'"score":1.0', b'"score":1.0,"score":1.0'))
                    (entry / 'result.json').write_bytes(value)
                    metadata = cache.decoded((entry / 'cache.json').read_bytes())
                    metadata['files']['result.json'] = cache.digest(value)
                    (entry / 'cache.json').write_bytes(cache.encoded(metadata))
                self.assertIsNone(self.cache.load(self.key, self.identity))
                self.assertFalse(entry.exists())

    def test_links_and_unsafe_root_do_not_modify_external_data(self):
        sentinel = Path(self.temp.name) / 'outside'
        sentinel.write_bytes(b'KEEP')
        sentinel.chmod(0o600)
        for link in ['symlink', 'hardlink']:
            with self.subTest(link=link):
                self.cache.store(self.key, self.identity, self.files)
                file = self.root / self.key / 'strategy.out'
                file.unlink()
                if link == 'symlink':
                    file.symlink_to(sentinel)
                else:
                    os.link(sentinel, file)
                self.assertIsNone(self.cache.load(self.key, self.identity))
                self.assertEqual(sentinel.read_bytes(), b'KEEP')
        root_link = Path(self.temp.name) / 'root-link'
        root_link.symlink_to(self.root)
        self.assertFalse(cache.ResultCache(root_link).store(self.key, self.identity, self.files))
        wrong = Path(self.temp.name) / 'not-cache'
        wrong.mkdir(mode=0o700)
        (wrong / 'existing').write_text('KEEP')
        self.assertFalse(cache.ResultCache(wrong).store(self.key, self.identity, self.files))
        self.assertEqual(sorted(p.name for p in wrong.iterdir()), ['existing'])
        self.root.chmod(0o755)
        self.assertIsNone(self.cache.load(self.key, self.identity))

    def test_expiry_entry_and_size_limits(self):
        self.cache.store(self.key, self.identity, self.files)
        old = time.time() - 8 * 86400
        os.utime(self.root / self.key, (old, old))
        self.assertIsNone(self.cache.load(self.key, self.identity))
        limited = cache.ResultCache(self.root, max_entries=1)
        limited.store(self.key, self.identity, self.files)
        old = time.time() - 20
        os.utime(self.root / self.key, (old, old))
        key, identity, files = fixture(1)
        self.assertTrue(limited.store(key, identity, files))
        self.assertFalse((self.root / self.key).exists())
        self.assertEqual(limited.load(key, identity), files)
        self.assertFalse(cache.ResultCache(self.root, max_bytes=10).store(key, identity, files))

    def test_competing_publish_is_complete_and_lock_contention_is_a_miss(self):
        context = multiprocessing.get_context('spawn')
        barrier, output = context.Barrier(2), context.Queue()
        workers = [context.Process(target=publish, args=(self.root, self.key, self.identity, self.files, barrier, output)) for _ in range(2)]
        for worker in workers:
            worker.start()
        results = [output.get(timeout=15) for _ in workers]
        for worker in workers:
            worker.join(timeout=15)
            self.assertEqual(worker.exitcode, 0)
        output.close()
        self.assertTrue(any(results))
        self.assertEqual(self.cache.load(self.key, self.identity), self.files)
        self.assertFalse(any(p.name.startswith('.pending-') for p in self.root.iterdir()))
        with self.cache._guard():
            self.assertIsNone(cache.ResultCache(self.root).load(self.key, self.identity))
            self.assertFalse(cache.ResultCache(self.root).store(self.key, self.identity, self.files))

    def test_keys_bind_actual_model_placements_and_binary(self):
        source = b'{"id":"TEST_ONLY"}'
        request = {'modelHash': cache.digest(source), 'inputHash': '1' * 64, 'placements': []}
        binary = Path(self.temp.name) / 'engine'
        binary.write_bytes(b'ENGINE_TEST_A')
        with patch.object(swmm, 'library_path', return_value=binary):
            key, identity = cache.computation_identity(source, request)
            self.assertEqual(key, cache.computation_identity(source, request)[0])
            self.assertNotEqual(key, cache.computation_identity(source, request | {'inputHash': '2' * 64})[0])
            self.assertNotEqual(key, cache.computation_identity(source, request | {'placements': [{'cellId': 'TEST'}]})[0])
            other_source = b'{"id":"OTHER_TEST_ONLY"}'
            self.assertNotEqual(key, cache.computation_identity(other_source, request | {'modelHash': cache.digest(other_source)})[0])
            binary.write_bytes(b'ENGINE_TEST_B')
            self.assertNotEqual(key, cache.computation_identity(source, request)[0])
            with self.assertRaises(ValueError):
                cache.computation_identity(source, request | {'modelHash': '3' * 64})
            with self.assertRaises(ValueError):
                cache.computation_identity(source, request | {'ownerId': 'NOT_ALLOWED'})
            with self.assertRaises(ValueError):
                self.cache.load('../outside', identity)

    def test_keys_bind_site_policy_and_validation_implementation(self):
        source = b'{"id":"TEST_ONLY"}'
        request = {'modelHash': cache.digest(source), 'inputHash': '1' * 64, 'placements': []}
        binary = Path(self.temp.name) / 'engine'
        binary.write_bytes(b'ENGINE_TEST_ONLY')
        with patch.object(swmm, 'library_path', return_value=binary):
            key = cache.computation_identity(source, request)[0]
            with patch.object(cache.suitability, 'POLICY_SHA256', '2' * 64):
                self.assertNotEqual(key, cache.computation_identity(source, request)[0])
            for module in (cache.placement_validation, cache.suitability):
                changed = Path(self.temp.name) / 'validation.py'
                changed.write_bytes(b'CHANGED_TEST_ONLY_VALIDATION')
                with patch.object(module, '__file__', str(changed)):
                    self.assertNotEqual(key, cache.computation_identity(source, request)[0])

    @unittest.skipUnless(swmm.library_path().exists(), 'EPA 엔진 빌드 필요')
    def test_current_restrictions_block_before_cache_read_or_engine_execution(self):
        for status in ('PROHIBITED', 'CONDITIONAL'):
            with self.subTest(status=status):
                model = json.loads((swmm.ROOT / 'data/models/seongsu-lab.json').read_bytes())
                next(cell for cell in model['cells'] if cell['id'] == 'G1')['siteEligibility'] = status
                source = cache.encoded(model)
                request = {'modelHash': cache.digest(source), 'inputHash': '1' * 64,
                           'placements': [{'cellId': 'G1', 'facilityType': 'RAIN_GARDEN', 'areaM2': 20}]}
                with patch.object(cache.ResultCache, 'load') as load, patch.object(swmm, 'experiment') as engine:
                    with self.assertRaisesRegex(cache.suitability.SiteSuitabilityError, 'SITE_SUITABILITY_RESTRICTED'):
                        cache.execute(source, request, Path(self.temp.name), self.root)
                    load.assert_not_called()
                    engine.assert_not_called()

    @unittest.skipUnless(swmm.library_path().exists(), 'EPA 엔진 빌드 필요')
    def test_real_engine_reuse_is_equal_and_target_request_and_files_are_independent(self):
        source = (swmm.ROOT / 'data/models/seongsu-lab.json').read_bytes()
        placements = [{'cellId': 'G1', 'facilityType': 'RAIN_GARDEN', 'areaM2': 40}]
        model_hash = cache.digest(source)
        request = {'placements': placements, 'modelHash': model_hash,
                   'inputHash': cache.digest((model_hash + '\n' + json.dumps(placements, separators=(',', ':'))).encode())}
        env = {k: v for k, v in os.environ.items() if k in ['PATH', 'LANG', 'LC_ALL']}
        env.update(PYTHONPATH=str(swmm.ROOT / 'simulation'), SWMM_LIBRARY=str(swmm.library_path()), SIMULATION_CACHE_PATH=str(self.root))
        results = []
        directories = []
        for label in ['first-owner', 'second-owner', 'disabled']:
            directory = Path(self.temp.name) / label
            directory.mkdir(mode=0o700)
            cache._write(directory / 'model-source.json', source)
            # 같은 물리 조건이라도 대상 작업의 요청 원문 보존 확인.
            raw_request = json.dumps(request, indent=len(directories) + 1).encode()
            cache._write(directory / 'request.json', raw_request)
            child_env = env | ({'SIMULATION_CACHE_ENABLED': 'false'} if label == 'disabled' else {})
            child = subprocess.run([sys.executable, '-m', 'waterleague_sim.run_job', str(directory)],
                                   env=child_env, capture_output=True, text=True, timeout=90)
            self.assertEqual(0, child.returncode, child.stderr[-3000:])
            self.assertEqual((directory / 'request.json').read_bytes(), raw_request)
            manifest = cache.decoded((directory / 'manifest.json').read_bytes())
            self.assertEqual(set(manifest), cache.FILES | {'request.json'})
            for name, value in manifest.items():
                self.assertEqual(cache.digest((directory / name).read_bytes()), value)
            results.append(cache.decoded((directory / 'result.json').read_bytes()))
            directories.append(directory)
        self.assertEqual([r['execution']['mode'] for r in results], ['COMPUTED', 'REUSED', 'COMPUTED'])
        for field in ['score', 'baseline', 'strategy', 'sensitivity', 'engine']:
            self.assertEqual(results[0][field], results[1][field])
            self.assertEqual(results[0][field], results[2][field])
        for name in cache.FILES:
            self.assertNotEqual((directories[0] / name).stat().st_ino, (directories[1] / name).stat().st_ino)
        (directories[1] / 'strategy.out').write_bytes(b'LOCAL_COPY_CHANGED')
        identity_key, identity = cache.computation_identity(source, request)
        self.assertEqual(self.cache.load(identity_key, identity)['strategy.out'], (directories[0] / 'strategy.out').read_bytes())
        limited = Path(self.temp.name) / 'limited-job'
        limited.mkdir(mode=0o700)
        cache._write(limited / 'model-source.json', source)
        cache._write(limited / 'request.json', cache.encoded(request))
        old_mask = os.umask(0o077)
        try:
            with patch.object(cache, 'MAX_ENTRY_BYTES', 1):
                uncached = cache.execute(source, request, limited, Path(self.temp.name) / 'limited-cache')
        finally:
            os.umask(old_mask)
        self.assertEqual(uncached['execution']['mode'], 'COMPUTED')
        self.assertEqual(uncached['strategy'], results[0]['strategy'])
