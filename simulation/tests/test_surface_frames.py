"""중심 수심·유속 프레임의 비개입·무결성·시간/영역 선택 검사."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from waterleague_sim.engine.flood_errors import FloodModelError
from waterleague_sim.engine.flood_process import EngineProcess
from waterleague_sim.engine.coupled_flood import run_coupled
from waterleague_sim.engine.surface_frame_reader import NativeFrameReader
from waterleague_sim.reference.flood_cases import mesh, coupled_limited_case

OUTPUT = {'schemaVersion': 1, 'type': 'NATIVE_CENTROID_FLOAT64', 'maxFrames': 1000, 'maxBytes': 8*1024**2}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class SurfaceFrameTests(unittest.TestCase):
    def test_exact_native_values_and_readonly_output(self):
        import numpy as np
        model = mesh(4, 2, 20, 10, water=lambda x, z: .1*(x < 10))
        model.update(schemaVersion=2, maxStepSeconds=.1)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            results = []
            for enabled in (False, True):
                path = root/str(enabled)
                value = model | ({'frameOutput': OUTPUT} if enabled else {})
                with EngineProcess('surface', value, path) as session:
                    initial = session.info['initial']
                    session.call('advance', 1.)
                    middle = session.call('advance', 1.)
                    session.call('advance', 1.)
                    results.append(session.call('finish'))
            self.assertEqual(results[0]['final'], results[1]['final'])
            self.assertEqual(results[0]['numericalQuality'], results[1]['numericalQuality'])
            reader = NativeFrameReader(root/'True', sha(root/'True/surface-result.json'))
            self.assertEqual(reader.times, [0., 1., 2., 3.])
            for index, state in [(0, initial), (2, middle), (3, results[1]['final'])]:
                frame = reader.frame(index)
                self.assertEqual(frame['depthM'], state['depthM'])
                self.assertEqual(frame['velocityXMps'], state['velocityXMps'])
                self.assertEqual(frame['velocityYMps'], state['velocityYMps'])
                self.assertEqual(frame['wholeDomainStorageM3'], state['storageM3'])
            selected = reader.visible_triangles([0., 0., 4., 4.])
            self.assertLess(len(selected), reader.count)
            sample = reader.at_time(2.5, triangles=selected)
            self.assertEqual(sample['ageSeconds'], .5)
            np.testing.assert_array_equal(sample['depthM'], np.asarray(middle['depthM'])[selected])
            self.assertFalse(reader.catalog['rankingEligible'])
            with self.assertRaisesRegex(FloodModelError, 'EXTRAPOLATION'):
                reader.at_time(3.01)
            with self.assertRaisesRegex(FloodModelError, 'SELECTION'):
                reader.frame(0, triangles=[0, 0])

    def test_hash_binding_and_lazy_frame_read(self):
        model = mesh(1, 1) | {'schemaVersion': 2, 'frameOutput': OUTPUT}
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()/'run'
            with EngineProcess('surface', model, root) as session:
                session.call('set_rainfall', [60., 60.])
                session.call('advance', 30.)
                session.call('advance', 30.)
                session.call('finish')
            expected = sha(root/'surface-result.json')
            original_result = (root/'surface-result.json').read_bytes()
            failed = json.loads(original_result) | {'numericalStatus': 'FAILED'}
            (root/'surface-result.json').write_text(json.dumps(failed))
            with self.assertRaisesRegex(FloodModelError, 'FAILED_RESULT'):
                NativeFrameReader(root, sha(root/'surface-result.json'))
            (root/'surface-result.json').write_bytes(original_result)
            reader = NativeFrameReader(root, expected)
            # 요청하지 않은 시각 파일을 삭제해도 현재 요청은 해당 프레임 하나만 읽는다.
            (root/'native-frames/frame-00002.bin').unlink()
            self.assertEqual(reader.frame(1)['timeSeconds'], 30.)
            with self.assertRaisesRegex(FloodModelError, 'FILE_INVALID'):
                reader.frame(2)
            file = root/'native-frames/frame-00001.bin'
            raw = file.read_bytes()
            file.write_bytes(b'X'+raw[1:])
            with self.assertRaisesRegex(FloodModelError, 'HASH_MISMATCH'):
                reader.frame(1)
            with self.assertRaisesRegex(FloodModelError, 'HASH_MISMATCH'):
                NativeFrameReader(root, '0'*64)
            file.unlink()
            file.symlink_to(root/'native-frames/frame-00000.bin')
            with self.assertRaisesRegex(FloodModelError, 'FILE_INVALID'):
                reader.frame(1)

    def test_output_limit_is_failure_without_silent_resolution_change(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            small = mesh(1, 1) | {'frameOutput': OUTPUT | {'maxBytes': 1}}
            with self.assertRaisesRegex(FloodModelError, 'BYTE_LIMIT'):
                with EngineProcess('surface', small, root/'bytes'):
                    pass
            limited = mesh(1, 1) | {'frameOutput': OUTPUT | {'maxFrames': 2}}
            with EngineProcess('surface', limited, root/'count') as session:
                session.call('advance', 1.)
                with self.assertRaisesRegex(FloodModelError, 'COUNT_LIMIT'):
                    session.call('advance', 1.)
            self.assertFalse((root/'count/native-frames/catalog.json').exists())
            self.assertFalse((root/'count/surface-result.json').exists())

    def test_coupled_exchange_frame_interval_does_not_change_physics(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            results, counts = [], []
            for index, interval in enumerate((100, 1000)):
                model = coupled_limited_case()
                model['surface'].update(schemaVersion=2, frameOutput=deepcopy(OUTPUT))
                model['frameIntervalMilliseconds'] = interval
                path = root/str(index)
                result = run_coupled(model, path)
                results.append(result)
                reader = NativeFrameReader(path/'surface', sha(path/'surface/surface-result.json'))
                frame = reader.at_time(result['durationSeconds'])
                self.assertAlmostEqual(frame['wholeDomainStorageM3'], result['balance']['surfaceStorageM3'], places=12)
                counts.append(len(reader.times))
                self.assertEqual(result['surfaceFrames']['catalogFile'], 'surface/native-frames/catalog.json')
            self.assertEqual(results[0]['balance'], results[1]['balance'])
            self.assertEqual(results[0]['surfaceNumericalQuality'], results[1]['surfaceNumericalQuality'])
            self.assertGreater(counts[0], counts[1])


if __name__ == '__main__':
    unittest.main()
