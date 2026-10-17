"""관망 수지·역류·API 단위·비개입 검증. 합성 사례는 운영 입력이 아님."""
from io import BytesIO
import math
from pathlib import Path
import subprocess
import tempfile
import unittest
from zipfile import ZipFile

from waterleague_sim.engine import network, swmm
from waterleague_sim.engine.flood_errors import FloodModelError
from waterleague_sim.reference.epa import read_sources
from waterleague_sim.reference.flood_cases import tank_input


@unittest.skipUnless(network.library_path().exists(), '관망 엔진 빌드 필요')
class NetworkTests(unittest.TestCase):
    def test_boundary_reversal_and_exact_si_inflow_preserve_volume(self):
        with tempfile.TemporaryDirectory() as root:
            with network.NetworkSession(tank_input(), Path(root) / 'reverse', evaluation_seconds=120) as s:
                # 원본 CMS 저장곡선의 EPA 체적 변환 반올림은 보정하지 않는다.
                self.assertAlmostEqual(s.initial['nodes']['TANK']['storageM3'], 10, delta=.002)
                s.set_outfall_head('OUT', 2)
                reverse = s.advance(30)
                self.assertLess(reverse['links']['PIPE']['flowM3s'], 0)
                self.assertGreater(reverse['nodes']['TANK']['storageM3'], 10)
                self.assertGreater(reverse['nodes']['OUT']['boundaryInflowM3'], 0)
                self.assertAlmostEqual(reverse['totals']['externalInflowM3'],
                                       reverse['nodes']['OUT']['boundaryInflowM3'], places=8)
                s.set_outfall_head('OUT', 0)
                s.set_inflow('TANK', .02)
                forward = s.advance(90)
                self.assertGreater(forward['links']['PIPE']['flowM3s'], 0)
                # API 유입도 첫 반시간과 마지막 반시간 사이의 엔진 적분량으로 확인한다.
                applied = forward['totals']['externalInflowM3'] - forward['nodes']['OUT']['boundaryInflowM3']
                self.assertAlmostEqual(applied, .02 * 90, delta=.002)
                result = s.finish()
                self.assertEqual(result['numericalStatus'], 'PASSED')
                self.assertLess(abs(result['final']['totals']['balanceResidualM3']), .15)
                self.assertEqual(len(result['forcing']), 3)

    def test_overflow_is_finite_and_cumulative_node_volume_matches_system(self):
        with tempfile.TemporaryDirectory() as root:
            with network.NetworkSession(tank_input(initial=0, full=.1), Path(root) / 'flood', evaluation_seconds=120) as s:
                s.set_inflow('TANK', 1)
                result = s.advance(120)
                total = result['totals']
                self.assertGreater(total['floodingM3'], 100)
                self.assertAlmostEqual(total['floodingM3'], result['nodes']['TANK']['floodingM3'], places=8)
                self.assertAlmostEqual(total['externalInflowM3'], 120, delta=.1)
                self.assertEqual(s.finish()['numericalStatus'], 'PASSED')

    def test_invalid_boundary_parallel_session_and_incomplete_result(self):
        with tempfile.TemporaryDirectory() as root:
            with network.NetworkSession(tank_input(), Path(root) / 'first', evaluation_seconds=120) as s:
                for name, flow in [('missing', 1), ('TANK', math.nan), ('TANK', -1), ('OUT', 1)]:
                    with self.assertRaises(FloodModelError):
                        s.set_inflow(name, flow)
                with self.assertRaises(FloodModelError):
                    s.set_outfall_head('TANK', 2)
                with self.assertRaisesRegex(FloodModelError, 'ALREADY_OPEN'):
                    with network.NetworkSession(tank_input(), Path(root) / 'second'):
                        pass
                s.advance(1)
                self.assertEqual(s.finish()['numericalStatus'], 'FAILED')
            with network.NetworkSession(tank_input(), Path(root) / 'third', evaluation_seconds=120) as s:
                s.advance(120)
                self.assertTrue(s.finish()['complete'])
            with self.assertRaisesRegex(FloodModelError, 'END_TRUNCATED'):
                with network.NetworkSession(tank_input(), Path(root) / 'truncated'):
                    pass

    @unittest.skipUnless((swmm.ROOT / 'tmp/epa-reference/applications.zip').exists(), '확보 EPA 원본 필요')
    def test_official_network_observer_does_not_change_stock_engine_output(self):
        source = swmm.ROOT / 'tmp/epa-reference/applications.zip'
        manifest, _ = read_sources(source)
        with ZipFile(source) as outer:
            with ZipFile(BytesIO(outer.read(manifest['nestedArchive']['member']))) as inner:
                inputs = {name: inner.read(name).decode('cp1252') for name in ('Example3.inp', 'Example8.inp')}
        with tempfile.TemporaryDirectory() as root:
            for name, inp in inputs.items():
                directory = Path(root) / name
                with network.NetworkSession(inp, directory) as s:
                    while s.snapshot()['totals']['timeSeconds'] < s.duration_seconds:
                        s.advance()
                    result = s.finish()
                subprocess.run([str(swmm.library_path().parent / 'runswmm'), str(directory / 'network.inp'),
                                str(directory / 'stock.rpt'), str(directory / 'stock.out')],
                               check=True, capture_output=True, timeout=30)
                self.assertEqual((directory / 'network.out').read_bytes(), (directory / 'stock.out').read_bytes())
                self.assertIn('routingContinuityPercent', result)
                self.assertNotEqual(result['final']['totals']['outflowM3'], 0)
