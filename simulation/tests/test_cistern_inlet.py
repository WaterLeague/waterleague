"""연결관 크기·역압·입구 월류와 강우 면적 보존의 실제 엔진 검사."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from waterleague_sim.engine.cistern_network import compile_cistern
from waterleague_sim.engine.cistern_inlet import compile_inlet
from waterleague_sim.engine.connected_storage import result_summary
from waterleague_sim.engine.flood_errors import FloodModelError
from waterleague_sim.engine.flood_process import EngineProcess
from waterleague_sim.ingestion.published_network import records
from waterleague_sim.reference.cistern_network import source, design, hydrology_series


PIPE = {'lengthM': 10., 'diameterM': .1, 'roughness': .013,
        'upstreamInvertM': 1., 'upstreamMaxDepthM': .3, 'downstreamInvertM': .8}


class CisternInletTests(unittest.TestCase):
    def test_invalid_geometry_and_source_names_cannot_silently_change_route(self):
        raw = source()
        spec = design(raw) | {'inletPipe': PIPE}
        derived, metadata = compile_cistern(raw, spec)
        sections = records(derived)[1]
        capture = next(r['tokens'] for r in sections['SUBCATCHMENTS'] if r['tokens'][0] == 'WLCT_Cistern_C')
        self.assertEqual(capture[2], 'WLCT_Cistern_U')
        self.assertEqual(metadata['inletPipe']['linkId'], 'WLCT_Cistern_I')
        self.assertEqual(compile_cistern(raw, spec), (derived, metadata))
        # 14.4−14.2의 이진 오차가 길이 0.2m인 경계 입력을 바꾸지 않는다.
        compile_inlet(PIPE | {'upstreamInvertM': 14.4, 'downstreamInvertM': 14.2, 'lengthM': .2},
                      'WLCT_Cistern', 13.5, 1.4)
        for patch in ({'lengthM': 0}, {'roughness': 0}, {'roughness': 2}, {'diameterM': .4},
                      {'downstreamInvertM': -.1}, {'upstreamInvertM': .5},
                      {'lengthM': .1}, {'upstreamMaxDepthM': float('nan')},
                      {'unexpected': 1}):
            with self.subTest(patch=patch), self.assertRaises(FloodModelError):
                compile_cistern(raw, spec | {'inletPipe': PIPE | patch})
        for value in (None, {}, False):
            with self.subTest(value=value), self.assertRaises(FloodModelError):
                compile_cistern(raw, spec | {'inletPipe': value})
        collision = raw + b'\n; WLCT_Cistern_U\n[COORDINATES]\nWLCT_Cistern_U 0 0\n'
        with self.assertRaisesRegex(FloodModelError, 'ID_COLLISION'):
            compile_cistern(collision, design(collision) | {'inletPipe': PIPE})

    def test_pipe_does_not_change_rain_area_or_surface_hydrology(self):
        raw = source(backwater=True)
        derived, _ = compile_cistern(raw, design(raw) | {'inletPipe': PIPE})
        with tempfile.TemporaryDirectory() as directory:
            baseline = hydrology_series(raw, Path(directory) / 'base')
            routed = hydrology_series(derived, Path(directory) / 'pipe')
        for key in baseline:
            for a, b in zip(baseline[key], routed[key]):
                self.assertAlmostEqual(a, b, delta=max(1e-9, abs(a) * 2e-7), msg=key)

    def test_capacity_backflow_and_inlet_flooding_are_retained_in_results(self):
        results = {}
        cases = [('wide', .1, 3600, 0, {}), ('narrow', .01, 3600, 0, {}),
                 ('backflow', .1, 0, 1.2, {}), ('replay', .1, 3600, 0, {}),
                 ('ordinary', .1, 600, 0, {}), ('rough', .1, 3600, 0, {'roughness': .1}),
                 ('long', .1, 3600, 0, {'lengthM': 20.}),
                 ('numerically-unstable', .1, 3600, 0, {'lengthM': 100.})]
        with tempfile.TemporaryDirectory() as directory:
            for label, diameter, rainfall, initial, patch in cases:
                raw = source(backwater=True).replace(b'00:00 3600', f'00:00 {rainfall}'.encode())
                spec = design(raw) | {'inletPipe': PIPE | {'diameterM': diameter} | patch,
                    'initialDepthM': initial, 'drain': {'mode': 'CLOSED_NO_WITHDRAWAL'}}
                derived, meta = compile_cistern(raw, spec)
                target = Path(directory) / label
                with EngineProcess('network', derived.decode(), target, native_duration=True) as process:
                    run = process.call('run', 1)['result']
                summary = result_summary(meta, run['initial'], run['final'])
                self.assertEqual(run['numericalStatus'],
                    'FAILED' if label == 'numerically-unstable' else 'PASSED', run['numericalQuality'])
                frames = [json.loads(line) for line in (target / 'network-frames.jsonl').read_text().splitlines()]
                results[label] = (summary, min(f['links']['WLCT_Cistern_I']['flowM3s'] for f in frames))
                inlet = summary['wholeRunLedger']['inletPipe']
                self.assertAlmostEqual(inlet['floodingM3'], run['final']['nodes']['WLCT_Cistern_U']['floodingM3'])
                self.assertEqual(inlet['numericalStatus'], 'FAILED' if inlet['floodingM3'] > 1e-9 else 'PASSED')
                if inlet['numericalStatus'] == 'FAILED':
                    self.assertEqual(summary['numericalStatus'], 'FAILED')
                self.assertIsNone(summary['wholeRunLedger']['facilities'][0]['reuseM3'])
                print(json.dumps({'case': label, 'networkStatus': run['numericalStatus'],
                    'ledger': summary['wholeRunLedger'], 'minimumInletFlowM3s': results[label][1],
                    'sourceNetworkSha256': meta['sourceNetworkSha256'],
                    'derivedNetworkSha256': meta['derivedNetworkSha256'],
                    'numericalQuality': run['numericalQuality']}, ensure_ascii=False))
        wide = results['wide'][0]['wholeRunLedger']
        narrow = results['narrow'][0]['wholeRunLedger']
        self.assertGreater(narrow['inletPipe']['floodingM3'], wide['inletPipe']['floodingM3'])
        self.assertGreater(wide['facilities'][0]['inflowM3'], narrow['facilities'][0]['inflowM3'])
        self.assertLess(results['backflow'][1], -1e-7)
        self.assertEqual(results['wide'], results['replay'])
        self.assertEqual(results['ordinary'][0]['numericalStatus'], 'PASSED')
        for case in ('rough', 'long'):
            self.assertLess(results[case][0]['wholeRunLedger']['facilities'][0]['inflowM3'],
                            wide['facilities'][0]['inflowM3'])


if __name__ == '__main__':
    unittest.main()
