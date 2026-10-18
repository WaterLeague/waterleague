"""펌프·지표의 내부 이송과 평가 경계·원 입력 변조 거부 검사."""
from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
import unittest

from waterleague_sim.engine.coupled_flood import run_coupled
from waterleague_sim.engine.coupled_pumps import compile
from waterleague_sim.engine.coupled_pump_network import library_path
from waterleague_sim.engine.flood_errors import FloodModelError
from waterleague_sim.engine.swmm import ROOT
from waterleague_sim.evaluation.coupled_adapter import file_digest
from waterleague_sim.evaluation.exception import EvaluationError
from waterleague_sim.reference.coupled_pumps import case, initialized
from simulation.tests.test_storage_composition import check_record


class CoupledPumpContractTests(unittest.TestCase):
    def test_source_binding_shared_ids_and_input_preservation(self):
        model = case()
        original = deepcopy(model)
        prepared, metadata = compile(model, model)
        self.assertEqual(model, original)
        self.assertEqual((prepared, metadata), compile(model, model))
        self.assertNotEqual(prepared['network']['inputText'], model['network']['inputText'])
        changed = deepcopy(model)
        changed['connectedPumpDesign']['sourceNetworkSha256'] = '0'*64
        with self.assertRaisesRegex(FloodModelError, 'SOURCE_BINDING_INVALID'):
            compile(changed, changed)
        changed = deepcopy(model)
        changed['connectedStorageDesign'] = {'placements': [{'id': 'lift'}]}
        with self.assertRaisesRegex(FloodModelError, 'SHARED_ID_CONFLICT'):
            compile(changed, changed)


@unittest.skipUnless(library_path().exists(), '펌프·지표 결합 빌드 필요')
class CoupledPumpNativeTests(unittest.TestCase):
    def root(self, variable):
        if target := os.environ.get(variable):
            path = Path(target).resolve()
        else:
            temporary = tempfile.TemporaryDirectory(dir=ROOT/'tmp', prefix='coupled-pumps-')
            self.addCleanup(temporary.cleanup)
            path = Path(temporary.name)/'runs'
        path.mkdir(parents=True, exist_ok=False)
        return path

    def test_exchange_window_replay_convergence_failure_and_reader(self):
        root = self.root('COUPLED_PUMP_EVIDENCE_DIR')
        old, _ = compile(case(), case())
        old.pop('connectedPumpDesign')
        models = {'baseline': case(pump=False), 'pump': case(), 'replay': case(),
            'display-interval': case(frame_ms=2000), 'old-observer': old,
            'exchange-50ms': case(exchange_ms=50), 'route-5ms': case(route_step=.005),
            'boundary-37ms': case(start_seconds=.037), 'start-zero': case(start_seconds=0)}
        results = {}
        for name, model in models.items():
            value = results[name] = run_coupled(model, root/name)
            self.assertEqual(value['numericalStatus'], 'PASSED', name)
            self.assertEqual(value['networkConvergence']['nonConvergedSteps'], 0, name)
            self.assertTrue(check_record(root/name)['complete'], name)
            self.assertAlmostEqual(value['balance']['exchangeCancellationResidualM3'], 0, places=10)
            print(name, value['numericalStatus'], flush=True)
        result = results['pump']
        self.assertGreater(result['balance']['networkToSurfaceM3'], 1)
        self.assertGreater(result['balance']['surfaceToNetworkM3'], 1)
        self.assertEqual(results['baseline']['balance']['networkToSurfaceM3'], 0)
        self.assertGreater(result['evaluationMetrics']['raw']['depthAreaTimeM3Hours'],
                           results['baseline']['evaluationMetrics']['raw']['depthAreaTimeM3Hours'])
        operation = result['connectedPumps']['operation']
        whole, evaluated = operation['pumps'][0], operation['evaluation']['pumps'][0]
        self.assertEqual((whole['startCount'], evaluated['startCount']), (1, 0))
        self.assertEqual((whole['observedSeconds'], evaluated['observedSeconds']), (600, 590))
        self.assertLess(evaluated['transferredM3'], whole['transferredM3'])
        zero = results['start-zero']['connectedPumps']['operation']
        for k, v in zero['evaluation']['pumps'][0].items():
            self.assertEqual(v, zero['pumps'][0][k], k)
        for name in ('replay', 'display-interval', 'old-observer'):
            self.assertEqual((root/'pump/network/network.out').read_bytes(),
                             (root/name/'network/network.out').read_bytes(), name)
            self.assertEqual(result['balance'], results[name]['balance'], name)
            self.assertEqual(result['evaluationMetrics'], results[name]['evaluationMetrics'], name)
        for name in ('replay', 'display-interval'):
            self.assertEqual(operation, results[name]['connectedPumps']['operation'])
        for name in ('exchange-50ms', 'route-5ms'):
            self.assertAlmostEqual(whole['transferredM3'],
                results[name]['connectedPumps']['operation']['pumps'][0]['transferredM3'], delta=.01)
            self.assertAlmostEqual(result['evaluationMetrics']['raw']['depthAreaTimeM3Hours'],
                results[name]['evaluationMetrics']['raw']['depthAreaTimeM3Hours'], delta=.002)
        with self.assertRaisesRegex(FloodModelError, 'UNMAPPED_NODE_FLOODING'):
            run_coupled(case(pressure_limit=.51), root/'delivery-overpressure')
        self.assertTrue((root/'delivery-overpressure').is_dir())
        self.check_tampering(root/'pump')
        summary = {'classification': 'PUBLIC_MANUFACTURER_CURVE_SYNTHETIC_NETWORK_SURFACE_NOT_SEOUL',
            'rankingEligible': False, 'siteValidation': False, 'exactReplayAndReadOnlyObserver': True,
            'deliveryOverpressure': 'REJECTED_UNMAPPED_NODE_FLOODING',
            'cases': {name: {k: v[k] for k in ('numericalStatus', 'networkConvergence', 'balance',
                'evaluationMetrics', 'connectedPumps') if k in v} for name, v in results.items()}}
        (root/'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n')

    def check_tampering(self, root):
        result_file = root/'coupled-result.json'
        result_bytes = result_file.read_bytes()
        for name, key, value, error in (
            ('connected-pump-design.json', 'originalNetworkSha256', '0'*64, 'PUMP_CONTEXT_MISMATCH'),
            ('pump-coupled-input.json', 'durationSeconds', 601, 'PUMP_CONTEXT_MISMATCH')):
            path = root/name
            original = path.read_bytes()
            try:
                changed = json.loads(original); changed[key] = value
                path.write_text(json.dumps(changed))
                result = json.loads(result_bytes); result['files'][name] = file_digest(path)
                result_file.write_text(json.dumps(result))
                with self.assertRaisesRegex(EvaluationError, error): check_record(root)
            finally:
                path.write_bytes(original); result_file.write_bytes(result_bytes)
        network_file = root/'network/network-result.json'
        original = network_file.read_bytes()
        try:
            network = json.loads(original)
            network['pumpOperation']['evaluation']['pumps'][0]['observedSeconds'] = 600
            network_file.write_text(json.dumps(network))
            result = json.loads(result_bytes)
            result['files']['network/network-result.json'] = file_digest(network_file)
            result['connectedPumps']['operation'] = network['pumpOperation']
            result_file.write_text(json.dumps(result))
            with self.assertRaisesRegex(EvaluationError, 'PUMP_OPERATION_INVALID'): check_record(root)
        finally:
            network_file.write_bytes(original); result_file.write_bytes(result_bytes)

    def test_evaluation_window_stops_without_stopping_hydraulics(self):
        root = self.root('COUPLED_PUMP_WINDOW_EVIDENCE_DIR')
        result = run_coupled(case(start_seconds=0, end_seconds=10), root/'ten-seconds')
        self.assertTrue(check_record(root/'ten-seconds')['complete'])
        self.assertEqual(result['numericalStatus'], 'PASSED')
        op = result['connectedPumps']['operation']
        whole, evaluated = op['pumps'][0], op['evaluation']['pumps'][0]
        self.assertEqual((whole['observedSeconds'], evaluated['observedSeconds']), (600, 10))
        self.assertEqual(evaluated['startCount'], 1)
        self.assertLess(evaluated['transferredM3'], whole['transferredM3'])

    def test_observed_warmup_preserves_state_and_rejects_unstable_startup(self):
        root = self.root('INITIALIZED_COUPLED_PUMP_EVIDENCE_DIR')
        lids = json.loads((Path(__file__).parent/'fixtures/connected-facilities-v1.json').read_bytes())
        result = run_coupled(initialized(lids), root/'combined')
        self.assertEqual(result['numericalStatus'], 'FAILED')
        self.assertGreater(result['networkConvergence']['nonConvergedSteps'], 0)
        record = check_record(root/'combined')
        self.assertTrue(record['complete'])
        self.assertEqual(record['numericalStatus'], 'FAILED')
        op = result['connectedPumps']['operation']
        self.assertEqual(op['evaluation']['startSeconds'], 604800)
        self.assertEqual(op['evaluation']['pumps'][0]['observedSeconds'], 21540)
        self.assertGreater(op['pumps'][0]['transferredM3'], 0)
        self.assertEqual(op['evaluation']['pumps'][0]['transferredM3'], op['pumps'][0]['transferredM3'])
        self.assertGreater(op['pumps'][0]['outsideHeadCurveSeconds'], 0)
        self.assertIsNone(op['pumps'][0]['shaftEnergyKwh'])
        self.assertEqual(len(result['connectedFacilities']['design']['facilities']), 4)
        self.assertGreater(result['connectedStorage']['evaluationLedger']['facilities'][0]['initialStorageM3'], 0)
        self.assertAlmostEqual(result['initialization']['evaluationLedger']['surface']['rainfallM3'], 850.)
        self.check_failed_promotion(root/'combined')
        (root/'summary.json').write_text(json.dumps({
            'classification': 'OBSERVED_RAIN_WEATHER_SYNTHETIC_FACILITIES_NOT_SEOUL_VALIDATION',
            'rankingEligible': False, 'numericalStatus': result['numericalStatus'],
            'balance': result['balance'], 'initialization': result['initialization'],
            'connectedPumps': result['connectedPumps']}, ensure_ascii=False, indent=2)+'\n')

    def check_failed_promotion(self, root):
        paths = [root/'network/network-result.json', root/'coupled-result.json']
        originals = [p.read_bytes() for p in paths]
        try:
            network, result = [json.loads(raw) for raw in originals]
            network['numericalStatus'] = result['numericalStatus'] = 'PASSED'
            paths[0].write_text(json.dumps(network))
            result['files']['network/network-result.json'] = file_digest(paths[0])
            paths[1].write_text(json.dumps(result))
            with self.assertRaisesRegex(EvaluationError, 'PUMP_STATUS_MISMATCH'): check_record(root)
        finally:
            for path, raw in zip(paths, originals): path.write_bytes(raw)


if __name__ == '__main__': unittest.main()
