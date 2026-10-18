"""원본 결속·합성 입력·동시 저류 수지·관측 초기화 검사."""
from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
import unittest

from waterleague_sim.engine.connected_storage import compile_storage
from waterleague_sim.engine.surface_basin import compile_basin
from waterleague_sim.engine.storage_composition import compose_storage
from waterleague_sim.engine.coupled_flood import run_coupled
from waterleague_sim.engine.flood_errors import FloodModelError
from waterleague_sim.evaluation.coupled_adapter import engine_signature, file_digest, read_coupled_record
from waterleague_sim.evaluation.exception import EvaluationError
from waterleague_sim.evaluation.values import digest
from waterleague_sim.ingestion.published_network import records
from waterleague_sim.ingestion.published_network import digest as bytes_digest
from waterleague_sim.reference.storage_composition import case, initialized
from simulation.tests.test_flood_attribution import policy

ROOT = Path(__file__).resolve().parents[2]


def prepared(model):
    basin, _ = compile_basin(model)
    raw, storage = compile_storage(model['network']['inputText'].encode(), model['connectedStorageDesign'])
    return basin, raw, storage


def check_record(path):
    result = json.loads((path/'coupled-result.json').read_bytes())
    network = json.loads((path/'network/network-result.json').read_bytes())
    surface = json.loads((path/'surface/surface-result.json').read_bytes())
    context = policy()['context'] | {
        'metricSpecificationSha256': digest(result['evaluationMetrics']['specification']),
        'engineSha256': engine_signature(network, surface, result)}
    return read_coupled_record(path, file_digest(path/'coupled-result.json'), context)


class StorageCompositionContractTests(unittest.TestCase):
    def test_source_binding_and_both_generated_networks_preserved(self):
        model = case()
        original = deepcopy(model)
        basin, raw, storage = prepared(model)
        combined, proof = compose_storage(model, basin, raw, storage)
        self.assertEqual(model, original)
        self.assertEqual((combined, proof), compose_storage(model, basin, raw, storage))
        source = records(model['network']['inputText'].encode())[1]
        target = records(combined)[1]
        for section, rows in source.items():
            self.assertEqual([r['tokens'] for r in rows], [r['tokens'] for r in target[section]
                if not r['tokens'][0].upper().startswith(('WLST_', 'WLBS_'))])
        self.assertEqual(storage['design'], model['connectedStorageDesign'])
        self.assertEqual(basin['surface']['rainfallOwner'], model['surface']['rainfallOwner'])
        self.assertEqual(basin['evaluationMetrics'], model['evaluationMetrics'])
        self.assertNotEqual(proof['storageNetworkSha256'], proof['composedNetworkSha256'])
        self.assertIn(b'WLBS_Pond_D', combined)
        self.assertIn(b'WLST_Tank_I', combined)

    def test_modified_source_and_invented_new_node_reference_rejected(self):
        model = case()
        basin, raw, storage = prepared(model)
        altered = deepcopy(basin)
        altered['network']['inputText'] += '\n; 변경된 파생 입력\n'
        with self.assertRaisesRegex(FloodModelError, 'BASIN_INPUT_MISMATCH'):
            compose_storage(model, altered, raw, storage)
        altered = deepcopy(model)
        altered['connectedStorageDesign']['sourceNetworkSha256'] = '0'*64
        pond = altered.pop('surfaceBasinDesign')
        pond['sourceModelSha256'] = digest(altered)
        altered['surfaceBasinDesign'] = pond
        with self.assertRaisesRegex(FloodModelError, 'STORAGE_DESIGN_SOURCE_BINDING_INVALID'):
            prepared(altered)
        altered = deepcopy(model)
        pond = altered.pop('surfaceBasinDesign')
        pond['placements'][0]['drain']['nodeId'] = 'WLST_Tank'
        pond['sourceModelSha256'] = digest(altered)
        altered['surfaceBasinDesign'] = pond
        with self.assertRaisesRegex(FloodModelError, 'INTERNAL_NODE_REQUIRED'):
            prepared(altered)

    def test_original_network_edit_cannot_be_disguised_as_storage_addition(self):
        model = case()
        basin, raw, storage = prepared(model)
        changed = raw.replace(b'DRAIN TANK RECEIVER BOTTOM', b'DRAIN RECEIVER TANK BOTTOM')
        self.assertNotEqual(changed, raw)
        storage['derivedNetworkSha256'] = bytes_digest(changed)
        with self.assertRaisesRegex(FloodModelError, 'COMPOSITION_SOURCE_MUTATION'):
            compose_storage(model, basin, changed, storage)


class StorageCompositionNativeTests(unittest.TestCase):
    def root(self, variable):
        if target := os.environ.get(variable):
            path = Path(target).resolve()
            self.assertFalse(path.exists())
        else:
            temp = tempfile.TemporaryDirectory(dir=ROOT/'tmp', prefix='storage-composition-')
            self.addCleanup(temp.cleanup)
            path = Path(temp.name)/'runs'
        path.mkdir()
        return path

    def test_interaction_native_balance_steps_replay_and_tamper_rejection(self):
        root = self.root('STORAGE_COMPOSITION_EVIDENCE_DIR')
        models = {'baseline': case(basin=False, storage=False), 'basin': case(storage=False),
            'storage': case(basin=False), 'combined': case(),
            'combined-50ms': case(exchange_ms=50), 'replay': case()}
        results = {}
        for name, model in models.items():
            path = root/name
            result = results[name] = run_coupled(model, path)
            self.assertEqual(result['numericalStatus'], 'PASSED', name)
            self.assertEqual(result['networkConvergence']['nonConvergedSteps'], 0)
            self.assertTrue(check_record(path)['complete'])
            self.assertAlmostEqual(result['balance']['surfaceRainfallM3'], .008, places=10)
            if 'connectedStorage' in result:
                self.assertEqual(result['connectedStorage']['numericalStatus'], 'PASSED')
                self.assertGreater(result['connectedStorage']['wholeRunLedger']['facilities'][0]['inflowM3'], 0)
            if 'surfaceBasins' in result:
                self.assertEqual(result['surfaceBasins']['additionalStorageInCoupledBalanceM3'], 0)
            print(name, result['numericalStatus'], flush=True)
        for name in ('network/network.out', 'surface/surface-result.json'):
            self.assertEqual((root/'combined'/name).read_bytes(), (root/'replay'/name).read_bytes())
        metrics = {name: value['evaluationMetrics']['raw'] for name, value in results.items()}
        interaction = {key: metrics['combined'][key]-metrics['basin'][key]
            -metrics['storage'][key]+metrics['baseline'][key] for key in metrics['baseline']}
        self.assertNotEqual(metrics['combined'], metrics['basin'])
        self.assertGreater(abs(interaction['outwardVolumeM3']), .001)
        step = {key: metrics['combined'][key]-metrics['combined-50ms'][key] for key in metrics['baseline']}
        self.assertLess(abs(step['outwardVolumeM3']), .001)
        proof = root/'combined/connected-design-composition.json'
        result_file = root/'combined/coupled-result.json'
        originals = proof.read_bytes(), result_file.read_bytes()
        try:
            altered = json.loads(originals[0])
            altered['sourceNetworkSha256'] = '0'*64
            proof.write_text(json.dumps(altered))
            result = deepcopy(results['combined'])
            result['files']['connected-design-composition.json'] = file_digest(proof)
            result_file.write_text(json.dumps(result))
            with self.assertRaisesRegex(EvaluationError, 'COMPOSITION_CONTEXT_MISMATCH'):
                check_record(proof.parent)
        finally:
            proof.write_bytes(originals[0]); result_file.write_bytes(originals[1])
        (root/'summary.json').write_text(json.dumps({'classification': 'NUMERICAL_TEST_NOT_SEOUL',
            'exactReplay': True, 'combinedMinusIndependentSum': interaction, 'step100Minus50': step,
            'cases': {name: {k:v[k] for k in ('numericalStatus', 'networkConvergence', 'balance',
                'evaluationMetrics')} for name,v in results.items()}}, indent=2)+'\n')

    def test_observed_initialization_keeps_both_storage_states_and_four_lids(self):
        root = self.root('INITIALIZED_STORAGE_COMPOSITION_EVIDENCE_DIR')
        lids = json.loads((Path(__file__).parent/'fixtures/connected-facilities-v1.json').read_bytes())
        result = run_coupled(initialized(lids), root/'combined')
        self.assertEqual(result['numericalStatus'], 'PASSED')
        self.assertEqual(result['networkConvergence']['nonConvergedSteps'], 0)
        self.assertTrue(check_record(root/'combined')['complete'])
        storage = result['connectedStorage']['evaluationLedger']
        self.assertEqual(storage['startSeconds'], 7*86400)
        self.assertGreater(storage['facilities'][0]['initialStorageM3'], 0)
        self.assertGreater(result['surfaceBasins']['evaluationInitial']['facilities'][0]['storageM3'], 0)
        self.assertEqual(len(result['connectedFacilities']['design']['facilities']), 4)
        self.assertAlmostEqual(result['initialization']['evaluationLedger']['surface']['rainfallM3'], 850.)
        self.assertGreater(result['balance']['surfaceRainfallM3'], 850.)


if __name__ == '__main__':
    unittest.main()
