"""유한 저류·원 관망 보존·역류·선행 상태·재현 묶음 검사."""
from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
import unittest

from waterleague_sim.engine.connected_storage import compile_storage, storage_ledger, result_summary
from waterleague_sim.engine.coupled_flood import run_coupled
from waterleague_sim.engine.flood_errors import FloodModelError
from waterleague_sim.engine.flood_process import EngineProcess
from waterleague_sim.evaluation.coupled_adapter import engine_signature, file_digest, read_coupled_record
from waterleague_sim.evaluation.exception import EvaluationError
from waterleague_sim.evaluation.values import digest as json_digest
from waterleague_sim.ingestion.published_network import records, digest
from waterleague_sim.reference.connected_storage import case, design, with_receiver
from waterleague_sim.reference.initialized_coupling import inputs
from simulation.tests.test_connected_facilities import baseline
from simulation.tests.test_flood_attribution import policy

ROOT = Path(__file__).resolve().parents[2]
LIDS = json.loads((Path(__file__).parent/'fixtures/connected-facilities-v1.json').read_text())


def check_record(path, result):
    network = json.loads((path/'network/network-result.json').read_text())
    surface = json.loads((path/'surface/surface-result.json').read_text())
    context = policy()['context'] | {
        'metricSpecificationSha256': json_digest(result['evaluationMetrics']['specification']),
        'engineSha256': engine_signature(network, surface, result)}
    return read_coupled_record(path, file_digest(path/'coupled-result.json'), context), context


class StorageContractTests(unittest.TestCase):
    def test_curve_integral_source_immutability_and_deterministic_compilation(self):
        model = case()
        source = model['network']['inputText'].encode().replace(b'\n', b'\r\n')
        request = design(source)
        request['placements'][0]['depthAreaCurve'] = [
            {'depthM': 0, 'areaM2': 2}, {'depthM': .5, 'areaM2': 3}, {'depthM': 1.4, 'areaM2': 4}]
        original = deepcopy(request)
        raw, metadata = compile_storage(source, request)
        self.assertEqual(request, original)
        self.assertAlmostEqual(metadata['facilities'][0]['capacityM3'], 4.4)
        self.assertFalse(metadata['rankingEligible'])
        self.assertEqual((raw, metadata), compile_storage(source, request))
        self.assertIn(b'WLST_Tank 0 1.4 0 TABULAR WLST_Tank_A 0 0\r\n', raw)
        before, after = records(source)[1], records(raw)[1]
        for section, rows in before.items():
            self.assertEqual([r['tokens'] for r in rows],
                [r['tokens'] for r in after[section] if not r['tokens'][0].upper().startswith('WLST_')])

    def test_unbound_unknown_unsafe_or_physically_disconnected_design_rejected(self):
        model = case()
        source = model['network']['inputText'].encode()
        request = model['connectedStorageDesign']
        for key, value in [('id', 1), ('id', 'x\n[FILES]'), ('id', 'A'*25), ('invertM', float('nan')),
                           ('initialDepthM', 2), ('invertM', 10**1000), ('cover', 'OPEN'), ('lining', 'UNKNOWN'),
                           ('depthAreaCurve', [{'depthM': .1, 'areaM2': 2}, {'depthM': 2, 'areaM2': 2}])]:
            altered = deepcopy(request)
            altered['placements'][0][key] = value
            with self.subTest(key=key), self.assertRaises(FloodModelError):
                compile_storage(source, altered)
        for key, value in [('nodeId', 'OUT'), ('nodeId', 'MISSING'), ('nodeId', 'TANK'),
                           ('diameterM', True), ('crestM', -1), ('crestM', 5), ('flapGate', 1)]:
            altered = deepcopy(request)
            altered['placements'][0]['drain'][key] = value
            with self.subTest(portKey=key), self.assertRaises(FloodModelError):
                compile_storage(source, altered)
        for changed in [source+b'; source changed\n', source.replace(b'FLOW_UNITS CMS', b'FLOW_UNITS'),
                        source.replace(b'DRAIN TANK RECEIVER', b'DRAIN RECEIVER TANK'),
                        source+b'\n[CONTROLS]\nRULE R\nIF NODE WLST_Tank DEPTH > 0\nTHEN LINK TAIL SETTING = 0\n']:
            altered = deepcopy(request)
            if not changed.endswith(b'; source changed\n'):
                altered['sourceNetworkSha256'] = digest(changed)
            with self.assertRaises(FloodModelError):
                compile_storage(changed, altered)
        disconnected = source.replace(b'[STORAGE]', b'[STORAGE]\nDEAD 0 5 0 FUNCTIONAL 0 0 1 0 0').replace(
            b'[ORIFICES]', b'[ORIFICES]\nBRANCH TANK DEAD SIDE 0 .65 NO 0')
        altered = deepcopy(request)
        altered['sourceNetworkSha256'] = digest(disconnected)
        altered['placements'][0]['drain']['nodeId'] = 'DEAD'
        with self.assertRaisesRegex(FloodModelError, 'DOWNSTREAM_CONNECTION_REQUIRED'):
            compile_storage(disconnected, altered)

    def test_native_node_accounting_excludes_warmup_and_keeps_flooding_failure(self):
        model = case()
        _, metadata = compile_storage(model['network']['inputText'].encode(), model['connectedStorageDesign'])
        def state(time, inflow, outflow, stored, flooded=0):
            return {'totals': {'timeSeconds': time}, 'nodes': {'WLST_Tank': {'type': 2,
                'statisticInflowIncludingInitialM3': inflow, 'statisticOutflowM3': outflow,
                'storageM3': stored, 'floodingM3': flooded}}}
        initial, final = state(10, 100, 99.8, .2), state(20, 103, 102.7, .3)
        ledger = storage_ledger(metadata, initial, final)
        self.assertEqual(ledger['numericalStatus'], 'PASSED')
        self.assertEqual(ledger['facilities'][0]['inflowM3'], 3)
        item = ledger['facilities'][0]
        self.assertEqual(item['nativeCapacityM3'], metadata['facilities'][0]['nativeCapacityM3'])
        self.assertAlmostEqual(item['initialAvailableM3'], item['nativeCapacityM3']-.2)
        self.assertAlmostEqual(item['finalAvailableM3'], item['nativeCapacityM3']-.3)
        self.assertAlmostEqual(ledger['facilities'][0]['balanceResidualM3'], 0)
        final['nodes']['WLST_Tank']['floodingM3'] = .1
        self.assertEqual(storage_ledger(metadata, initial, final)['numericalStatus'], 'FAILED')
        with tempfile.TemporaryDirectory() as temp:
            model.pop('evaluationMetrics')
            with self.assertRaisesRegex(FloodModelError, 'STORAGE_METRICS_REQUIRED'):
                run_coupled(model, Path(temp)/'invalid')
            self.assertFalse((Path(temp)/'invalid').exists())


class StorageNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        target = os.environ.get('CONNECTED_STORAGE_EVIDENCE_DIR')
        if target:
            cls.root = Path(target).resolve()
            if cls.root.exists():
                raise ValueError('기존 재현 실행 덮어쓰기 금지')
            cls.root.mkdir(parents=True)
        else:
            cls.temp = tempfile.TemporaryDirectory(dir=ROOT/'tmp', prefix='storage-')
            cls.root = Path(cls.temp.name)
            cls.addClassCleanup(cls.temp.cleanup)

    def test_coupled_fill_emergency_backflow_flap_convergence_and_replay(self):
        baseline_model = case()
        baseline_model.pop('connectedStorageDesign')
        cases = {'baseline': baseline_model, 'normal': case(), 'replay': case(),
            'normal-1ms': case(route_ms=1), 'backwater-failed-2ms': case(backwater=True),
            'backwater-1ms': case(backwater=True, route_ms=1), 'flap': case(backwater=True, flap=True)}
        results, frames, contexts = {}, {}, {}
        for name, model in cases.items():
            original = deepcopy(model)
            path = self.root/name
            result = results[name] = run_coupled(model, path)
            self.assertEqual(model, original)
            expected = 'FAILED' if name == 'backwater-failed-2ms' else 'PASSED'
            self.assertEqual(result['numericalStatus'], expected, name)
            record, contexts[name] = check_record(path, result)
            self.assertEqual(record['numericalStatus'], expected)
            frames[name] = [json.loads(row) for row in (path/'network-frames.jsonl').read_text().splitlines()]
            if name != 'baseline':
                ledger = result['connectedStorage']['wholeRunLedger']['facilities'][0]
                self.assertLessEqual(max(f['nodes']['WLST_Tank']['storageM3'] for f in frames[name]),
                                     ledger['capacityM3']+1e-8)
                self.assertEqual(ledger['floodingM3'], 0)
                self.assertGreater(ledger['inflowM3'], 0)
                self.assertGreater(ledger['outflowIncludingFloodingM3'], 0)
        self.assertEqual((self.root/'normal/network/network.out').read_bytes(),
                         (self.root/'replay/network/network.out').read_bytes())
        self.assertEqual(results['normal']['connectedStorage'], results['replay']['connectedStorage'])
        self.assertEqual(contexts['baseline']['engineSha256'], contexts['normal']['engineSha256'])
        self.assertGreater(max(f['links']['WLST_Tank_O']['flowM3s'] for f in frames['normal']), .001)
        for link in ('WLST_Tank_D', 'WLST_Tank_O'):
            self.assertLess(min(f['links'][link]['flowM3s'] for f in frames['backwater-1ms']), -1e-6)
            self.assertGreaterEqual(min(f['links'][link]['flowM3s'] for f in frames['flap']), 0)
        self.assertGreater(results['backwater-failed-2ms']['networkConvergence']['nonConvergedSteps'], 0)
        self.assertEqual(results['backwater-failed-2ms']['evaluationMetrics']['status'], 'FAILED_DIAGNOSTIC')
        delta = {k: results['normal']['evaluationMetrics']['raw'][k]
                 -results['normal-1ms']['evaluationMetrics']['raw'][k]
                 for k in results['normal']['evaluationMetrics']['raw']}
        self.assertLess(abs(delta['outwardVolumeM3']), .001)
        self.assertLess(abs(delta['depthAreaTimeM3Hours']), .001)
        self.assertNotEqual(results['baseline']['evaluationMetrics']['raw'], results['normal']['evaluationMetrics']['raw'])
        path = self.root/'normal/coupled-result.json'
        original = path.read_bytes()
        changed = deepcopy(results['normal'])
        changed['connectedStorage']['wholeRunLedger']['facilities'][0]['finalStorageM3'] += 1
        try:
            path.write_text(json.dumps(changed))
            with self.assertRaisesRegex(EvaluationError, 'STORAGE_CONTEXT_MISMATCH'):
                check_record(path.parent, changed)
        finally:
            path.write_bytes(original)
        network_path = self.root/'normal/network/network-result.json'
        input_path = self.root/'normal/network/network.inp'
        network_bytes, input_bytes = network_path.read_bytes(), input_path.read_bytes()
        try:
            input_path.write_bytes(input_bytes.replace(b'WLST_Tank 0 1.4', b'WLST_Tank 0 1.5'))
            altered_network = json.loads(network_bytes)
            altered_network['files']['network.inp'] = file_digest(input_path)
            network_path.write_text(json.dumps(altered_network))
            changed = deepcopy(results['normal'])
            changed['files']['network/network.inp'] = file_digest(input_path)
            changed['files']['network/network-result.json'] = file_digest(network_path)
            path.write_text(json.dumps(changed))
            with self.assertRaisesRegex(EvaluationError, 'STORAGE_NATIVE_INPUT_MISMATCH'):
                check_record(path.parent, changed)
        finally:
            path.write_bytes(original)
            network_path.write_bytes(network_bytes)
            input_path.write_bytes(input_bytes)
        (self.root/'summary.json').write_text(json.dumps({'classification': 'NUMERICAL_TEST_NOT_SEOUL',
            'normal2msMinus1ms': delta, 'cases': {name: {k: row[k] for k in
                ('numericalStatus', 'balance', 'networkConvergence', 'evaluationMetrics')}
                for name, row in results.items()}}, ensure_ascii=False, indent=2)+'\n')

    def test_public_network_geometry_preserved_and_storage_node_ledger(self):
        source = baseline()
        request = design(source, inlet='J1', receiver='J2', invert=16, depth=5, area=100,
                         inlet_crest=18.5, drain_crest=16.2, overflow_crest=18.5)
        raw, metadata = compile_storage(source, request)
        before, after = records(source)[1], records(raw)[1]
        for section in before:
            self.assertEqual([r['tokens'] for r in before[section]],
                [r['tokens'] for r in after[section] if not r['tokens'][0].upper().startswith('WLST_')])
        path = self.root/'public-seocho'
        path.mkdir()
        (path/'original.inp').write_bytes(source)
        (path/'design.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2)+'\n')
        with EngineProcess('network', raw.decode(), path/'network', native_duration=True) as process:
            result = process.call('run', 300)['result']
        summary = result_summary(metadata, result['initial'], result['final'])
        (path/'storage-result.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n')
        self.assertEqual(result['convergence']['nonConvergedSteps'], 0)
        self.assertEqual(result['numericalStatus'], 'PASSED')
        self.assertGreater(summary['wholeRunLedger']['facilities'][0]['inflowM3'], 0)
        self.assertFalse(summary['rankingEligible'])

    def test_capacity_exceeded_without_surface_connection_remains_failed(self):
        model = case(route_ms=1)
        row = model['connectedStorageDesign']['placements'][0]
        row.update(depthAreaCurve=[{'depthM': 0, 'areaM2': .1}, {'depthM': .35, 'areaM2': .1}])
        row['inlet']['crestM'] = .05
        row['overflow']['crestM'] = .2
        path = self.root/'unmapped-overflow'
        with self.assertRaisesRegex(FloodModelError, 'COUPLED_UNMAPPED_NODE_FLOODING'):
            run_coupled(model, path)
        failure = json.loads((path/'coupled-failure.json').read_text())
        self.assertGreater(failure['lastNetwork']['totals']['floodingM3'], 0)
        self.assertFalse((path/'coupled-result.json').exists())

    def test_observed_initialization_keeps_storage_lids_network_and_surface_together(self):
        model = with_receiver(inputs(LIDS))
        text = model['network']['inputText'].replace('RECEIVER 0 5 0 FUNCTIONAL 0 0 1',
                                                   'RECEIVER 0 10 0 FUNCTIONAL 0 0 1000')
        model['network']['inputText'] = text
        request = design(text.encode(), area=100, depth=4, inlet_crest=.05,
                         drain_crest=.02, overflow_crest=3)
        model['connectedStorageDesign'] = request
        path = self.root/'observed-7d'
        result = run_coupled(model, path)
        self.assertEqual(result['numericalStatus'], 'PASSED')
        self.assertEqual(check_record(path, result)[0]['numericalStatus'], 'PASSED')
        self.assertEqual(len(result['connectedFacilities']['final']), 4)
        storage = result['connectedStorage']
        self.assertEqual(storage['evaluationLedger']['startSeconds'], 7*86400)
        self.assertEqual(storage['evaluationLedger']['endSeconds'], 7*86400+359*60)
        self.assertGreater(storage['evaluationLedger']['facilities'][0]['initialStorageM3'], 0)
        self.assertLess(storage['evaluationLedger']['facilities'][0]['inflowM3'],
                        storage['wholeRunLedger']['facilities'][0]['inflowM3'])
        self.assertAlmostEqual(result['initialization']['evaluationLedger']['surface']['rainfallM3'], 1700.)
        initialized = json.loads((path/'initialized-coupled-input.json').read_text())
        self.assertIn('WLST_Tank', initialized['network']['inputText'])
        self.assertEqual(json.loads((path/'coupled-input.json').read_text()), model)


if __name__ == '__main__':
    unittest.main()
