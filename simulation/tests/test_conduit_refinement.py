"""관로 분할의 형상·수치 절점·실패 원장 보존 검사."""
from copy import deepcopy
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from waterleague_sim.engine.flood_errors import FloodModelError
from waterleague_sim.engine.inlet_experiment import prepare, run, assess_result
from waterleague_sim.engine.inlet_network import library_path
from waterleague_sim.engine.swmm import ROOT
from waterleague_sim.ingestion.conduit_refinement import refine, assess_virtual_nodes
from waterleague_sim.ingestion.published_network import records, digest
from waterleague_sim.reference.connected_inlets import case


def request(raw, count=16):
    return {'schemaVersion': 1, 'sourceNetworkSha256': digest(raw),
        'segmentsByConduit': {k: count for k in ('CHANNEL', 'CONTINUATION', 'PIPE')},
        'minimumNumericalNodeAreaM2': .0001}


class RefinementContractTests(unittest.TestCase):
    def test_total_length_cross_section_gradient_and_terminal_id_preserved(self):
        raw, _ = case()
        design = request(raw)
        original = deepcopy(design)
        derived, metadata = refine(raw, design)
        self.assertEqual(design, original)
        self.assertEqual((derived, metadata), refine(raw, design))
        before, after = records(raw)[1], records(derived)[1]
        links = {r['tokens'][0]: r['tokens'] for r in after['CONDUITS']}
        shapes = {r['tokens'][0]: r['tokens'][1:] for r in after['XSECTIONS']}
        nodes = {r['tokens'][0]: r['tokens'] for name in ('JUNCTIONS','OUTFALLS') for r in after[name]}
        for row in metadata['conduits']:
            self.assertAlmostEqual(sum(float(links[k][3]) for k in row['segments']), row['originalLengthM'])
            self.assertEqual(row['segments'][-1], row['originalConduitId'])
            self.assertEqual(links[row['segments'][0]][1], row['originalNodes'][0])
            self.assertEqual(links[row['segments'][-1]][2], row['originalNodes'][1])
            for link in row['segments']:
                self.assertEqual(shapes[link], row['originalCrossSection'])
                self.assertEqual(float(links[link][4]), row['originalRoughness'])
                z0,z1 = (float(nodes[k][1]) for k in links[link][1:3])
                self.assertAlmostEqual((z0-z1)/float(links[link][3]),
                    (row['originalInvertM'][0]-row['originalInvertM'][1])/row['originalLengthM'])
            if row['originalCrossSection'][0] == 'CIRCULAR':
                for name in row['numericalNodes']:
                    node = nodes[name]
                    self.assertAlmostEqual(sum(float(node[i]) for i in (1,2,4)),
                                           row['closedConduitMaximumHeadM'])
        for section in ('DWF','OUTFALLS','REPORT','STREETS'):
            self.assertEqual([r['tokens'] for r in before[section]], [r['tokens'] for r in after[section]])
        self.assertIn(b'HEAD_TOLERANCE 0.000001', derived)
        self.assertFalse(metadata['rankingEligible'])

    def test_unbound_unsupported_or_invented_geometry_rejected(self):
        raw, _ = case()
        for change in (raw+b'; changed\n', raw.replace(b'CHANNEL A B 50 0.016 0 0',b'CHANNEL A B 50 0.016 1 0'),
                       raw.replace(b'A 1.5 1 0 0 0',b'A 1.5 1 0.1 0 0')):
            design = request(raw if change.endswith(b'changed\n') else change)
            with self.assertRaises(FloodModelError): refine(change, design)
        for value in (0, float('nan'), True):
            design = request(raw); design['minimumNumericalNodeAreaM2'] = value
            with self.assertRaises(FloodModelError): refine(raw, design)
        design = request(raw); design['segmentsByConduit']['MISSING'] = 3
        with self.assertRaises(FloodModelError): refine(raw, design)
        for suffix in (b'\n[LOSSES]\nCHANNEL 0.5 0 0 NO 0\n',
                       b'\n[CONTROLS]\nRULE R1\nIF CONDUIT CHANNEL FLOW > 1\n',
                       b'\n[VERTICES]\nCHANNEL 1 2\n'):
            changed = raw+suffix
            with self.assertRaises(FloodModelError): refine(changed, request(changed))
        changed = raw.replace(b'FLOW_UNITS CMS', b'FLOW_UNITS')
        with self.assertRaises(FloodModelError): refine(changed, request(changed))
        changed = raw.replace(b'BYPASS 0.5 FREE', b'BYPASS 0.5 FIXED')
        self.assertNotEqual(raw, changed)
        with self.assertRaises(FloodModelError): refine(changed, request(changed))

    def test_inlet_rebound_only_after_original_design_validation(self):
        raw, design = case()
        numerical = {'id': 'diagnostic-v1', 'options': {'SURCHARGE_METHOD': 'SLOT'}}
        prepared, meta = prepare(raw, design, request(raw), numerical)
        self.assertEqual(meta['sourceDesign'], design)
        self.assertEqual(meta['derivedNetworkSha256'], digest(prepared))
        self.assertTrue(meta['numerical']['hydraulicInputValuesUnchanged'])
        self.assertTrue(meta['numerical']['hydraulicApproximationChanged'])
        self.assertIn(b'HEAD_TOLERANCE 0.000001', prepared)
        for bad in ('missing', '0'*64):
            design['sourceNetworkSha256'] = bad
            with self.assertRaises(FloodModelError): prepare(raw, design, request(raw), numerical)

    def test_unmapped_numerical_node_overflow_blocks_result(self):
        raw, _ = case(); _, meta = refine(raw, request(raw))
        nodes = {name: {'floodingM3': 0.} for row in meta['conduits'] for name in row['numericalNodes']}
        result = {'final': {'nodes': nodes}}
        self.assertEqual(assess_virtual_nodes(meta, result)['status'], 'PASSED')
        nodes[next(iter(nodes))]['floodingM3'] = .000001
        self.assertEqual(assess_virtual_nodes(meta, result)['status'], 'FAILED')

    def test_native_facility_or_metric_failure_not_hidden_by_routing_balance(self):
        raw, _ = case(); _, meta = refine(raw, request(raw))
        nodes = {name: {'floodingM3': 0.} for row in meta['conduits'] for name in row['numericalNodes']}
        native = {'final': {'nodes': nodes}, 'numericalQuality': {'failureReasons': []},
            'facilityQuality': {'status': 'PASSED'}, 'evaluationMetrics': {'complete': True},
            'numericalStatus': 'PASSED'}
        self.assertEqual(assess_result({'refinement': meta}, native)['numericalStatus'], 'PASSED')
        for field, value, code in (
            ('facilityQuality', {'status': 'FAILED'}, 'CONNECTED_FACILITY_BALANCE_FAILED'),
            ('evaluationMetrics', {'complete': False}, 'OUTFALL_METRICS_INCOMPLETE'),
            ('numericalStatus', 'FAILED', 'NATIVE_NUMERICAL_FAILURE')):
            changed = deepcopy(native); changed[field] = value
            actual = assess_result({'refinement': meta}, changed)
            self.assertEqual(actual['numericalStatus'], 'FAILED')
            self.assertIn(code, actual['failureReasons'])


@unittest.skipUnless(library_path().exists(), '빗물받이 관측 엔진 필요')
class RefinementNativeTests(unittest.TestCase):
    def test_explicit_profiles_native_output_replay_and_failures_preserved(self):
        output = os.environ.get('REFINED_INLET_EVIDENCE_DIR')
        if output:
            root = Path(output).resolve(); root.mkdir(parents=True, exist_ok=False)
        else:
            temporary = tempfile.TemporaryDirectory(dir=ROOT/'tmp', prefix='refined-inlets-')
            self.addCleanup(temporary.cleanup); root = Path(temporary.name)
        results = {}
        for name, options, count, step, method in (
            ('grade', {}, 16, .01, 'SLOT'), ('replay', {}, 16, .01, 'SLOT'),
            ('street', {'street': True}, 16, .01, 'SLOT'),
            ('clogged', {'clogged': 90.}, 16, .01, 'SLOT'),
            ('sag', {'placement': 'ON_SAG'}, 16, .01, 'SLOT'),
            ('backflow', {'sewer_inflow': .2}, 16, .01, 'SLOT'),
            ('spatial-half', {}, 32, .01, 'SLOT'),
            ('temporal-half', {}, 16, .005, 'SLOT'),
            ('extran', {}, 16, .01, 'EXTRAN')):
            raw, design = case(**options)
            numerical = {'id': 'explicit-refinement-v1', 'options': {'ROUTING_STEP': step,
                'MINIMUM_STEP': step, 'MAX_TRIALS': 200, 'SURCHARGE_METHOD': method}}
            result, native = run(raw, design, request(raw, count), numerical, root/name,
                                 frame_seconds=1 if name == 'replay' else 60)
            results[name] = result, native
            self.assertEqual(result['nativeResultSha256'], digest((root/name/'network/network-result.json').read_bytes()))
            self.assertFalse(result['rankingEligible'])
            self.assertEqual(result['numericalStatus'], 'PASSED' if not result['failureReasons'] else 'FAILED')
            print(name, result['numericalStatus'], native['convergence']['nonConvergedSteps'],
                  native['numericalQuality']['routingBalance']['residualM3'], flush=True)
        normal = results['grade'][1]['inletOperation']['inlets'][0]
        self.assertGreater(normal['capturedM3'], 0)
        self.assertLess(results['clogged'][1]['inletOperation']['inlets'][0]['capturedM3'], normal['capturedM3'])
        self.assertLess(results['backflow'][1]['inletOperation']['inlets'][0]['netTransferToSewerM3'], 0)
        for name in ('grade', 'street'):
            self.assertEqual(results[name][0]['numericalStatus'], 'PASSED')
            self.assertEqual(results[name][0]['virtualNodes']['floodingM3'], 0)
        for name in ('clogged', 'sag', 'backflow', 'spatial-half', 'extran'):
            self.assertEqual(results[name][0]['numericalStatus'], 'FAILED')
        self.assertIn('UNMAPPED_COMPUTATIONAL_NODE_FLOODING', results['extran'][0]['failureReasons'])
        self.assertEqual(results['grade'][1]['inletOperation'], results['replay'][1]['inletOperation'])
        self.assertEqual((root/'grade/network/network.out').read_bytes(), (root/'replay/network/network.out').read_bytes())
        official = root/'official-engine'; official.mkdir()
        subprocess.run([str(ROOT/'tmp/swmm-build/install/bin/runswmm'),
            str(root/'grade/network/network.inp'), str(official/'network.rpt'), str(official/'network.out')],
            check=True, stdout=subprocess.DEVNULL)
        self.assertEqual((root/'grade/network/network.out').read_bytes(), (official/'network.out').read_bytes())


if __name__ == '__main__': unittest.main()
