"""출구 접속관의 물수지·역류·미연결 월류에 대한 수치 진단."""
import json
from pathlib import Path
import tempfile
import unittest

from waterleague_sim.engine.cistern_network import compile_cistern
from waterleague_sim.engine.cistern_outlet import compile_outlet
from waterleague_sim.engine.connected_storage import result_summary
from waterleague_sim.engine.flood_errors import FloodModelError
from waterleague_sim.engine.flood_process import EngineProcess
from waterleague_sim.ingestion.published_network import records
from waterleague_sim.reference.cistern_network import source, design, hydrology_series

PIPE = {'lengthM': 10., 'diameterM': .1, 'roughness': .013,
        'upstreamInvertM': 0., 'upstreamMaxDepthM': 1.4, 'downstreamInvertM': 0.}


class CisternOutletTests(unittest.TestCase):
    def test_routes_both_ports_through_distinct_pipes_and_rejects_unbound_geometry(self):
        raw = source()
        spec = design(raw) | {'drainPipe': PIPE, 'overflowPipe': PIPE}
        derived, meta = compile_cistern(raw, spec)
        sections = records(derived)[1]
        self.assertEqual(compile_cistern(raw, spec), (derived, meta))
        self.assertIn('[CONDUITS]', meta['source']['sections'])
        for kind, suffix in (('drain', 'D'), ('overflow', 'O')):
            port = next(r['tokens'] for r in sections['ORIFICES'] if r['tokens'][0] == 'WLCT_Cistern_' + suffix)
            self.assertEqual(port[1:3], ['WLCT_Cistern', 'WLCT_Cistern_' + suffix + 'J'])
            self.assertEqual(meta['outletPipes'][kind]['receiverNodeId'], 'TANK')
        for patch in ({'lengthM': 0}, {'diameterM': 0}, {'roughness': 0},
                      {'upstreamInvertM': .1}, {'downstreamInvertM': -.1},
                      {'upstreamMaxDepthM': .01}, {'downstreamInvertM': .1},
                      {'lengthM': float('nan')}, {'unexpected': 1}):
            with self.subTest(patch=patch), self.assertRaises(FloodModelError):
                compile_cistern(raw, spec | {'drainPipe': PIPE | patch})
        for value in (None, {}, False):
            with self.subTest(value=value), self.assertRaises(FloodModelError):
                compile_cistern(raw, spec | {'overflowPipe': value})
        with self.assertRaisesRegex(FloodModelError, 'CLOSED_DRAIN_PIPE'):
            compile_cistern(raw, spec | {'drain': {'mode': 'CLOSED_NO_WITHDRAWAL'}})
        collision = raw + b'\n[COORDINATES]\nWLCT_Cistern_OC 0 0\n'
        with self.assertRaisesRegex(FloodModelError, 'ID_COLLISION'):
            compile_cistern(collision, design(collision) | {'overflowPipe': PIPE})
        # 십진 경계에서 높이차와 관 길이가 같은 경우도 유효하다.
        compile_outlet(PIPE | {'lengthM': .2, 'upstreamInvertM': 14.4, 'downstreamInvertM': 14.2},
            'WLCT_Cistern', 'D', {'crestM': 14.4, 'diameterM': .1}, 'N', 14., 2.)

    def test_surface_rainfall_and_runoff_are_unchanged(self):
        raw = source(backwater=True)
        derived, _ = compile_cistern(raw, design(raw) | {'drainPipe': PIPE, 'overflowPipe': PIPE})
        with tempfile.TemporaryDirectory() as directory:
            before = hydrology_series(raw, Path(directory) / 'base')
            after = hydrology_series(derived, Path(directory) / 'pipe')
        for key in before:
            for a, b in zip(before[key], after[key]):
                self.assertAlmostEqual(a, b, delta=max(1e-9, abs(a) * 2e-7), msg=key)

    def test_engine_preserves_backflow_and_withholds_unconnected_flooding(self):
        results = {}
        with tempfile.TemporaryDirectory() as directory:
            for label, diameter, initial, rainfall in (
                ('wide', .1, 1.2, 0), ('narrow', .001, 1.2, 0),
                ('backflow', .1, 0, 0), ('replay', .1, 1.2, 0),
                ('rain', .1, 0, 600), ('flood', .001, 1.2, 0),
            ):
                raw = source(backwater=label == 'backflow').replace(b'00:00 3600', f'00:00 {rainfall}'.encode())
                spec = design(raw, flap=label != 'backflow') | {'initialDepthM': initial,
                    'drainPipe': PIPE | {'diameterM': diameter,
                        'upstreamMaxDepthM': .075 if label == 'flood' else 1.4}, 'overflowPipe': PIPE}
                derived, meta = compile_cistern(raw, spec)
                target = Path(directory) / label
                with EngineProcess('network', derived.decode(), target, native_duration=True) as process:
                    run = process.call('run', 1)['result']
                summary = result_summary(meta, run['initial'], run['final'])
                frames = [json.loads(line) for line in (target / 'network-frames.jsonl').read_text().splitlines()]
                flows = [f['links']['WLCT_Cistern_DC']['flowM3s'] for f in frames]
                for kind, pipe in summary['wholeRunLedger']['outletPipes'].items():
                    self.assertEqual(pipe['floodingM3'], run['final']['nodes'][pipe['nodeId']]['floodingM3'])
                    self.assertEqual(pipe['numericalStatus'], 'FAILED' if pipe['floodingM3'] > 1e-9 else 'PASSED')
                    if pipe['numericalStatus'] == 'FAILED':
                        self.assertEqual(summary['numericalStatus'], 'FAILED')
                results[label] = (summary, min(flows), max(flows), run['numericalStatus'])
                print(json.dumps({'case': label, 'ledger': summary['wholeRunLedger'],
                    'minimumDrainPipeFlowM3s': min(flows), 'maximumDrainPipeFlowM3s': max(flows),
                    'networkStatus': run['numericalStatus'], 'quality': run['numericalQuality'],
                    'sourceNetworkSha256': meta['sourceNetworkSha256'],
                    'derivedNetworkSha256': meta['derivedNetworkSha256']}))
        self.assertEqual(results['wide'], results['replay'])
        self.assertLess(results['backflow'][1], -1e-7)
        self.assertGreater(results['wide'][2], results['narrow'][2])
        self.assertEqual(results['wide'][3], 'PASSED')
        # 이 진단의 건습 전환과 초기 역압은 기존 수치 허용 기준을 넘으므로 실패를 보존한다.
        self.assertEqual(results['rain'][3], 'FAILED')
        self.assertEqual(results['backflow'][3], 'FAILED')
        self.assertEqual(results['flood'][0]['numericalStatus'], 'FAILED')
        self.assertGreater(results['flood'][0]['wholeRunLedger']['outletPipes']['drain']['floodingM3'], 0)


if __name__ == '__main__':
    unittest.main()
