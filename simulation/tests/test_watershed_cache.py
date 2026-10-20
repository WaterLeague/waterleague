"""관망 계산 캐시의 실제 엔진 일치·조건 분리·손상 복구 검사."""
from copy import deepcopy
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from waterleague_sim import watershed_cache as network_cache
from waterleague_sim import result_cache as cache
from waterleague_sim.engine import facility_metrics
from waterleague_sim.engine.flood_errors import FloodModelError
from waterleague_sim.engine.swmm import ROOT
from test_facility_metrics import MODEL


def request(placements='SYNTHETIC_CACHE_TEST_ONLY'):
    model = 'a'*64
    return {'modelHash': model, 'placements': placements,
            'inputHash': cache.digest((model+'\n'+placements).encode())}


@unittest.skipUnless(facility_metrics.library_path().exists(), '관망 지표 엔진 필요')
class WatershedCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT/'tmp', prefix='network-cache-')
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.root = self.directory/'cache'
        self.old_mask = os.umask(0o077)
        self.addCleanup(os.umask, self.old_mask)
        self.engine = facility_metrics.identity()
        self.raw = MODEL.encode()
        self.key, self.source = network_cache.identity(
            request(), self.raw, 'facility_metrics', self.engine)

    def run_case(self, name, root=True):
        return network_cache.run(request(), self.raw, 'facility_metrics', self.engine,
                                 self.directory/name, self.root if root else None)

    def test_native_reuse_equals_uncached_and_keeps_independent_files(self):
        first, computed = self.run_case('first')
        with patch.object(network_cache, 'EngineProcess', side_effect=AssertionError('새 계산 금지')):
            second, reused = self.run_case('second')
        third, disabled = self.run_case('disabled', root=False)
        self.assertEqual([v['mode'] for v in (computed, reused, disabled)],
                         ['COMPUTED', 'REUSED', 'COMPUTED'])
        self.assertEqual(computed['computationKey'], reused['computationKey'])
        self.assertEqual(first, second)
        for field in set(first)-{'files'}:
            self.assertEqual(first[field], third[field], field)
        for name in network_cache.FILES:
            a, b = self.directory/'first'/name, self.directory/'second'/name
            self.assertEqual(a.read_bytes(), b.read_bytes())
            self.assertNotEqual(a.stat().st_ino, b.stat().st_ino)
        (self.directory/'second/network.out').write_bytes(b'LOCAL_COPY_CHANGED')
        self.assertNotEqual(network_cache.NetworkCaseCache(self.root).load(
            self.key, self.source)['network.out'], b'LOCAL_COPY_CHANGED')
        for name in ('network.inp', 'network.out', 'network-frames.jsonl'):
            self.assertEqual((self.directory/'first'/name).read_bytes(),
                             (self.directory/'disabled'/name).read_bytes())
        self.assertNotIn('request.json', {p.name for p in (self.root/self.key).iterdir()})

    def test_corrupt_file_forces_recalculation_and_failed_or_unbound_result_is_not_stored(self):
        first, _ = self.run_case('first')
        (self.root/self.key/'network.out').write_bytes(b'CORRUPTED')
        second, execution = self.run_case('second')
        self.assertEqual(execution['mode'], 'COMPUTED')
        self.assertEqual(first['final'], second['final'])
        store = network_cache.NetworkCaseCache(self.root)
        files = store.load(self.key, self.source)
        for change in ({'numericalStatus': 'FAILED'}, {'complete': False},
                       {'ownerId': 'NOT_ALLOWED'}, {'engine': {}},
                       {'files': {}}, {'forcing': [{'timeSeconds': 1}]}):
            with self.subTest(change=change):
                modified = files | {'network-result.json': cache.encoded(first | change)}
                self.assertFalse(store.store(self.key, self.source, modified))
        self.assertFalse(store.store(self.key, self.source, files | {'request.json': b'{}'}))
        with patch.object(cache, 'MAX_ENTRY_BYTES', 1):
            self.assertFalse(store.store(self.key, self.source, files))

    def test_identity_binds_exact_input_request_code_engine_and_runtime(self):
        def key(**changes):
            args = {'request': request(), 'raw': self.raw, 'engine_kind': 'facility_metrics',
                    'engine': self.engine} | changes
            return network_cache.identity(**args)[0]
        self.assertEqual(key(), self.key)
        for change in ({'raw': self.raw+b'\n'}, {'request': request('OTHER_TEST_DESIGN')},
                       {'engine': self.engine | {'binarySha256': 'b'*64}},
                       {'engine_kind': 'pump_network'}):
            self.assertNotEqual(key(**change), self.key)
        with patch.object(network_cache, 'implementation_hash', return_value='b'*64):
            self.assertNotEqual(key(), self.key)
        with patch.object(network_cache.platform, 'machine', return_value='TEST_OTHER_MACHINE'):
            self.assertNotEqual(key(), self.key)
        with self.assertRaises(FloodModelError):
            key(request=request() | {'inputHash': 'b'*64})
        with self.assertRaises(FloodModelError):
            key(request=request() | {'ownerId': 'NOT_ALLOWED'})
        with patch.dict(os.environ, {'SIMULATION_CACHE_ENABLED': 'false'}):
            self.assertIsNone(network_cache.configured_root())
        with patch.dict(os.environ, {'SIMULATION_CACHE_ENABLED': 'true',
                                    'WATERSHED_CACHE_PATH': str(self.root)}):
            self.assertEqual(network_cache.configured_root(), self.root)

    def test_current_design_validation_runs_before_cache(self):
        from waterleague_sim.run_watershed_job import calculate
        from test_watershed_cistern import design, packed
        value = deepcopy(design())
        value['placements'][0]['parameters']['nativeSeepageMmH'] = 1000
        with patch.object(network_cache.NetworkCaseCache, 'load') as load:
            with self.assertRaises(FloodModelError):
                calculate(packed(value), self.directory/'invalid', self.root)
            load.assert_not_called()

    def test_links_expiry_and_locked_cache_leave_outputs_available(self):
        import time
        self.run_case('first')
        store = network_cache.NetworkCaseCache(self.root)
        sentinel = self.directory/'outside'
        cache._write(sentinel, b'KEEP')
        target = self.root/self.key/'network.out'
        target.unlink()
        target.symlink_to(sentinel)
        self.assertIsNone(store.load(self.key, self.source))
        self.assertEqual(sentinel.read_bytes(), b'KEEP')
        _, rebuilt = self.run_case('rebuilt')
        self.assertEqual(rebuilt['mode'], 'COMPUTED')
        with store._guard():
            _, locked = self.run_case('locked')
        self.assertEqual(locked['mode'], 'COMPUTED')
        old = time.time()-8*86400
        os.utime(self.root/self.key, (old, old))
        self.assertIsNone(store.load(self.key, self.source))

    def test_distinct_cache_marker_cannot_remove_other_profile_files(self):
        from test_result_cache import fixture
        key, source, files = fixture()
        existing = cache.ResultCache(self.root)
        self.assertTrue(existing.store(key, source, files))
        self.assertIsNone(network_cache.NetworkCaseCache(self.root).load(self.key, self.source))
        self.assertEqual(existing.load(key, source), files)
        separate = self.directory/'network-cache'
        network_cache.run(request(), self.raw, 'facility_metrics', self.engine,
                          self.directory/'network', separate)
        self.assertIsNone(cache.ResultCache(separate).load(key, source))
        self.assertIsNotNone(network_cache.NetworkCaseCache(separate).load(self.key, self.source))

    def test_changed_implementation_is_not_published_or_cached(self):
        with patch.object(network_cache, 'implementation_hash', side_effect=['a'*64, 'b'*64]):
            with self.assertRaisesRegex(FloodModelError, 'WATERSHED_CACHE_CODE_CHANGED'):
                self.run_case('changed')
        self.assertFalse(any(p.is_dir() and len(p.name) == 64 for p in self.root.iterdir()))
