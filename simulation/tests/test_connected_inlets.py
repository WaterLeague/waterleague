"""빗물받이 원본 보존·실제 EPA 포착/반환·관측기 독립성 검사."""
from copy import deepcopy
import json
import os
import subprocess
from pathlib import Path
import tempfile
import unittest

from waterleague_sim.engine.connected_inlets import compile_inlets
from waterleague_sim.engine.flood_errors import FloodModelError
from waterleague_sim.engine.flood_process import EngineProcess
from waterleague_sim.engine.inlet_network import library_path
from waterleague_sim.engine.swmm import ROOT
from waterleague_sim.ingestion.published_network import records, digest
from waterleague_sim.reference.connected_inlets import case


class InletContractTests(unittest.TestCase):
    def test_compile_preserves_source_and_requires_real_existing_channel(self):
        for street in (False, True):
            raw, design = case(street=street)
            preserved = deepcopy(design)
            value, meta = compile_inlets(raw, design)
            self.assertEqual(design, preserved)
            before, after = records(raw)[1], records(value)[1]
            for key, rows in before.items(): self.assertEqual(rows, after[key])
            self.assertEqual(meta['sourceNetworkSha256'], digest(raw))
            self.assertIsNone(meta['completeInstalledCostKrw'])
            self.assertEqual((value, meta), compile_inlets(raw, design))
        for key, value in [('captureNodeId', 'B'), ('captureNodeId', 'SEWER'), ('conduitId', 'PIPE'),
                           ('cloggedPercent', 100), ('cloggedPercent', float('nan')),
                           ('numberPerSide', True), ('numberPerSide', 0), ('placement', 'AUTO'),
                           ('id', 'x\n[FILES]')]:
            raw, design = case(); design['placements'][0][key] = value
            with self.subTest(key=key), self.assertRaises(FloodModelError): compile_inlets(raw, design)
        raw, design = case()
        with self.assertRaises(FloodModelError): compile_inlets(raw+b'; altered\n', design)
        design['placements'] *= 2
        with self.assertRaises(FloodModelError): compile_inlets(raw, design)
        raw, design = case(); design['placements'][0]['shape']['widthM'] = 3
        with self.assertRaisesRegex(FloodModelError, 'WIDTH_EXCEEDS'): compile_inlets(raw, design)


@unittest.skipUnless(library_path().exists(), '빗물받이 관측 엔진 필요')
class InletNativeTests(unittest.TestCase):
    def test_native_capture_backflow_replay_and_failed_balance_not_promoted(self):
        output = os.environ.get('INLET_EVIDENCE_DIR')
        if output:
            root = Path(output).resolve(); root.mkdir(parents=True, exist_ok=False)
        else:
            temporary = tempfile.TemporaryDirectory(dir=ROOT/'tmp', prefix='inlets-')
            self.addCleanup(temporary.cleanup); root = Path(temporary.name)
        cases = [('grade', {}, 'inlet_network', 60), ('replay', {}, 'inlet_network', 1),
            ('clogged', {'clogged': 90.}, 'inlet_network', 60),
            ('sag', {'placement': 'ON_SAG'}, 'inlet_network', 60),
            ('backflow', {'sewer_inflow': .2}, 'inlet_network', 60),
            ('street', {'street': True}, 'inlet_network', 60)]
        results = {}
        for name, options, engine, frame in cases:
            original, design = case(**options)
            raw, meta = compile_inlets(original, design)
            target = root/name; target.mkdir()
            (target/'original.inp').write_bytes(original)
            (target/'design.json').write_text(json.dumps(design, ensure_ascii=False, indent=2)+'\n')
            (target/'transformation.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2)+'\n')
            with EngineProcess(engine, raw.decode(), target/'network', native_duration=True) as process:
                results[name] = process.call('run', frame)['result']
            print(name, results[name]['numericalStatus'], flush=True)
        normal = results['grade']['inletOperation']['inlets'][0]
        self.assertGreater(normal['capturedM3'], 0)
        self.assertLess(results['clogged']['inletOperation']['inlets'][0]['capturedM3'], normal['capturedM3'])
        self.assertGreater(results['backflow']['inletOperation']['inlets'][0]['backflowM3'], 0)
        self.assertEqual(results['backflow']['final']['nodes']['S']['floodingSeconds'], 0)
        self.assertGreater(results['backflow']['final']['nodes']['S']['statisticFloodingM3'], 0)
        self.assertGreater(results['sag']['inletOperation']['inlets'][0]['capturedM3'], 0)
        self.assertGreater(results['street']['inletOperation']['inlets'][0]['capturedM3'], 0)
        for other in ('replay',):
            self.assertEqual((root/'grade/network/network.out').read_bytes(),
                             (root/other/'network/network.out').read_bytes())
            self.assertEqual(results['grade']['final'], results[other]['final'])
            self.assertEqual(results['grade']['evaluationMetrics'], results[other]['evaluationMetrics'])
        self.assertEqual(results['grade']['inletOperation'], results['replay']['inletOperation'])
        original = root/'official-engine'; original.mkdir()
        source = root/'grade/network/network.inp'
        subprocess.run([str(ROOT/'tmp/swmm-build/install/bin/runswmm'), str(source),
            str(original/'network.rpt'), str(original/'network.out')], check=True, stdout=subprocess.DEVNULL)
        self.assertEqual((root/'grade/network/network.out').read_bytes(), (original/'network.out').read_bytes())
        # 짧은 건조 시작 개수로는 공식 엔진에서도 수지가 실패한다. 관측기 검사를 물리 통과로 바꾸지 않는다.
        for result in results.values():
            seconds = [n['floodingSeconds'] for n in result['final']['nodes'].values()]
            duration = result['evaluationMetrics']['floodingDuration']['floodingSeconds']
            self.assertGreaterEqual(duration + 1e-6, max(seconds))
            self.assertLessEqual(duration, sum(seconds) + 1e-6)
            self.assertEqual(result['numericalStatus'], 'FAILED')
            self.assertIn('ROUTING_VOLUME_RESIDUAL_EXCEEDED', result['numericalQuality']['failureReasons'])


if __name__ == '__main__': unittest.main()
