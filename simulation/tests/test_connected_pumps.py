"""공개 펌프 곡선의 원본 보존·운전 범위·하류 영향·내부 이송 검사."""
from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
import unittest

from waterleague_sim.engine.connected_pumps import compile_pumps, catalog, CATALOG, CATALOG_HASH
from waterleague_sim.engine.flood_errors import FloodModelError
from waterleague_sim.engine.flood_process import EngineProcess
from waterleague_sim.engine.pump_network import library_path
from waterleague_sim.engine.swmm import ROOT
from waterleague_sim.ingestion.published_network import records, digest
from waterleague_sim.reference.connected_pumps import case


class PumpContractTests(unittest.TestCase):
    def test_public_curve_units_and_source_preserving_compile(self):
        raw, design = case()
        original = deepcopy(design)
        derived, meta = compile_pumps(raw, design)
        self.assertEqual(design, original)
        self.assertEqual((derived, meta), compile_pumps(raw, design))
        self.assertEqual(digest(CATALOG.read_bytes()), CATALOG_HASH)
        curve = catalog()
        self.assertEqual((curve['frequencyHz'], curve['speedRpm'], curve['bladeAngleDeg']), (50, 1450, 17))
        self.assertEqual(curve['points'][0]['flowM3h'], 700)
        self.assertEqual(curve['points'][-1]['flowM3h'], 1000)
        self.assertTrue(all(a['headM'] > b['headM'] for a, b in zip(curve['points'], curve['points'][1:])))
        before, after = records(raw)[1], records(derived)[1]
        for section, rows in before.items():
            actual = [r['tokens'] for r in after[section] if not r['tokens'][0].startswith('WLPU_')
                      and r['tokens'][0] != 'FORCE_MAIN_EQUATION']
            self.assertEqual(actual, [r['tokens'] for r in rows])
        self.assertFalse(meta['rankingEligible'])
        self.assertIsNone(meta['completeInstalledCostKrw'])
        self.assertIn(b'FORCE_MAIN_EQUATION D-W', derived)
        self.assertAlmostEqual(meta['facilities'][0]['flowRangeM3s'][0], 700/3600)

    def test_unsafe_disconnected_unbound_and_conflicting_design_rejected(self):
        raw, request = case()
        for key, value in [('id', 'x\n[FILES]'), ('id', 4), ('fromNode', 'O'), ('toNode', 'O'),
            ('toNode', 'S'), ('curveId', 'UNKNOWN'), ('stopDepthM', 0), ('startDepthM', 1),
            ('initialStatus', 'MAYBE'), ('startDepthM', float('nan')), ('startDepthM', True)]:
            d = deepcopy(request); d['placements'][0][key] = value
            with self.subTest(key=key), self.assertRaises(FloodModelError): compile_pumps(raw, d)
        for key, value in [('diameterM', 0), ('roughnessMm', 0), ('lengthM', -1),
            ('pressureHeadLimitM', .2), ('entranceLoss', -1), ('checkValve', 1), ('evidence', '')]:
            d = deepcopy(request); d['placements'][0]['delivery'][key] = value
            with self.subTest(key=key), self.assertRaises(FloodModelError): compile_pumps(raw, d)
        for change in [raw+b'; changed\n', raw.replace(b'FLOW_UNITS CMS', b'FLOW_UNITS CFS'),
                       raw.replace(b'[OPTIONS]', b'[OPTIONS]\nFORCE_MAIN_EQUATION H-W').replace(
                           b'TAIL CIRCULAR 2', b'TAIL FORCE_MAIN 2')]:
            d = deepcopy(request)
            if not change.endswith(b'; changed\n'): d['sourceNetworkSha256'] = digest(change)
            with self.assertRaises(FloodModelError): compile_pumps(change, d)
        d = deepcopy(request); d['placements'].append(deepcopy(d['placements'][0]))
        with self.assertRaises(FloodModelError): compile_pumps(raw, d)
        d = deepcopy(request); d['placements'][0]['fromNode'] = 'R'; d['placements'][0]['toNode'] = 'S'
        with self.assertRaisesRegex(FloodModelError, 'DOWNSTREAM_REQUIRED'): compile_pumps(raw, d)
        changed = raw.replace(b'[OPTIONS]', b'[OPTIONS]\nFORCE_MAIN_EQUATION H-W')
        d = deepcopy(request); d['sourceNetworkSha256'] = digest(changed)
        derived, meta = compile_pumps(changed, d)
        self.assertIn(b'FORCE_MAIN_EQUATION D-W', derived)
        self.assertEqual(meta['forceMainEquation'], {'original': 'H-W', 'applied': 'D-W', 'existingForceMains': False})


@unittest.skipUnless(library_path().exists(), '펌프 관측 빌드 필요')
class PumpNativeTests(unittest.TestCase):
    def test_native_head_loss_controls_failures_convergence_and_replay(self):
        target = os.environ.get('PUMP_EVIDENCE_DIR')
        if target:
            root = Path(target).resolve(); root.mkdir(parents=True, exist_ok=False)
        else:
            temporary = tempfile.TemporaryDirectory(dir=ROOT/'tmp', prefix='pump-')
            self.addCleanup(temporary.cleanup); root = Path(temporary.name)
        results = {}
        cases = [('normal', {}, 60, 'pump_network'), ('replay', {}, 1, 'pump_network'),
                 ('old-observer', {}, 60, 'facility_metrics'),
                 ('higher-tail', {'tail': 6}, 60, 'pump_network'),
                 ('long-pipe', {'length': 200}, 60, 'pump_network'),
                 ('outside-head', {'tail': 9}, 60, 'pump_network'),
                 ('delivery-flood', {'pressure_limit': .51}, 60, 'pump_network'),
                 ('dry', {'initial': .5}, 60, 'pump_network'),
                 ('half-step', {'step': .025}, 60, 'pump_network')]
        for name, options, interval, engine in cases:
            source, design = case(**options)
            raw, meta = compile_pumps(source, design)
            directory = root/name
            directory.mkdir()
            (directory/'original.inp').write_bytes(source)
            (directory/'design.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2)+'\n')
            (directory/'curve.json').write_bytes(CATALOG.read_bytes())
            with EngineProcess(engine, raw.decode(), directory/'network', native_duration=True) as p:
                results[name] = p.call('run', interval)['result']
            self.assertEqual(results[name]['convergence']['nonConvergedSteps'], 0, name)
        self.assertEqual(results['normal']['pumpOperation'], results['replay']['pumpOperation'])
        for name in ('replay', 'old-observer'):
            self.assertEqual((root/'normal/network/network.out').read_bytes(), (root/name/'network/network.out').read_bytes())
        def pump(name): return results[name]['pumpOperation']['pumps'][0]
        for name in ('normal', 'replay', 'higher-tail', 'dry', 'half-step'):
            self.assertEqual(results[name]['numericalStatus'], 'PASSED', name)
            self.assertEqual(pump(name)['outsideHeadCurveSeconds'], 0)
        self.assertAlmostEqual(pump('normal')['transferredM3'], 80, delta=.02)
        self.assertEqual(pump('normal')['startCount'], 1)
        self.assertLess(results['normal']['final']['nodes']['S']['depthM'], 1.2)
        self.assertEqual(results['normal']['final']['links']['WLPU_Lift']['setting'], 0)
        self.assertEqual(pump('dry')['transferredM3'], 0)
        self.assertEqual(results['delivery-flood']['numericalStatus'], 'FAILED')
        self.assertGreater(pump('delivery-flood')['deliveryFloodingM3'], 0)
        self.assertEqual(pump('delivery-flood')['deliveryStatus'], 'FAILED')
        self.assertGreater(pump('higher-tail')['runningSeconds'], pump('normal')['runningSeconds'])
        self.assertGreater(pump('higher-tail')['shaftEnergyKwh'], pump('normal')['shaftEnergyKwh'])
        for name in ('long-pipe', 'outside-head'):
            self.assertEqual(results[name]['numericalStatus'], 'FAILED')
            self.assertGreater(pump(name)['outsideHeadCurveSeconds'], 0)
            self.assertIsNone(pump(name)['shaftEnergyKwh'])
        for key in ('transferredM3', 'shaftEnergyKwh'):
            self.assertAlmostEqual(pump('normal')[key], pump('half-step')[key], delta=.0001)
        self.assertIsNone(pump('normal')['electricEnergyKwh'])
        self.assertEqual(pump('normal')['cavitationStatus'], 'NOT_EVALUATED')
        summary = {'classification': 'PUBLIC_MANUFACTURER_CURVE_SYNTHETIC_NETWORK_NUMERICAL_TEST',
            'catalogHash': CATALOG_HASH, 'engine': results['normal']['engine'],
            'outIdentity': {name: digest((root/name/'network/network.out').read_bytes()) for name in results},
            'cases': {name: {key: value for key, value in result.items() if key in ('numericalStatus',
                'pumpOperation', 'numericalQuality', 'convergence', 'evaluationMetrics')} for name, result in results.items()},
            'rankingEligible': False, 'siteValidation': False}
        (root/'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n')


if __name__ == '__main__': unittest.main()
