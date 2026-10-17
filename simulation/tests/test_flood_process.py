"""동시에 살아 있는 두 엔진의 상태·실패·종료 격리 검사."""
from importlib.util import find_spec
from pathlib import Path
import tempfile
import unittest

from waterleague_sim.engine.flood_process import EngineProcess
from waterleague_sim.engine.network import library_path
from waterleague_sim.reference.flood_cases import mesh, tank_input


@unittest.skipUnless(find_spec('anuga') and library_path().exists(), '관망·지표 엔진 설치 필요')
class FloodProcessTests(unittest.TestCase):
    def test_concurrent_native_runtimes_keep_independent_state(self):
        model = mesh(5, 5, 5, 5)
        with tempfile.TemporaryDirectory() as root:
            with EngineProcess('network', tank_input(), Path(root) / 'network', evaluation_seconds=120) as network:
                with EngineProcess('surface', model, Path(root) / 'surface') as surface:
                    self.assertNotEqual(network.process.pid, surface.process.pid)
                    surface.call('set_rainfall', [60.] * len(model['triangles']))
                    network.call('set_outfall_head', 'OUT', 2)
                    for _ in range(12):
                        network_state = network.call('advance', 10)
                        surface_state = surface.call('advance', 10)
                    self.assertEqual(network_state['totals']['timeSeconds'], surface_state['timeSeconds'])
                    self.assertGreater(network_state['nodes']['OUT']['boundaryInflowM3'], 0)
                    self.assertAlmostEqual(surface_state['storageM3'], .05, places=9)
                    self.assertTrue(network.call('finish')['complete'])
                    self.assertEqual(surface.call('finish')['numericalStatus'], 'PASSED')
            self.assertIsNone(network.process)
            self.assertIsNone(surface.process)
