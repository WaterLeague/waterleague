"""관측 선행 이용조·공동 LID·지표의 연속 상태와 원문 결속 검사."""
from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from waterleague_sim.engine.coupled_cistern import compile, facilities
from waterleague_sim.engine.coupled_flood import run_coupled
from waterleague_sim.engine.flood_errors import FloodModelError
from waterleague_sim.evaluation.coupled_adapter import file_digest, read_coupled_record
from waterleague_sim.evaluation.exception import EvaluationError
from waterleague_sim.forcing.coupled_initialization import prepare_initialized_coupling
from waterleague_sim.ingestion import live
from waterleague_sim.ingestion.published_network import records
from waterleague_sim.reference.cistern_network import design
from waterleague_sim.reference.initialized_coupling import inputs
from simulation.tests.test_initialized_coupling import DESIGN
from simulation.tests.test_live_coupled_facilities import context

ROOT = Path(__file__).resolve().parents[2]


def model(*, shared=False, closed=False, seed=.3, days=7):
    lid = deepcopy(DESIGN) if shared else None
    if shared:
        lid['placements'] = lid['placements'][:1]
    value = inputs(lid, days=days)
    value['connectedCisternDesign'] = design(value['network']['inputText'].encode()) | {
        'schemaVersion': 3 if shared else 2, 'initialDepthM': seed}
    if closed:
        value['connectedCisternDesign']['drain'] = {'mode': 'CLOSED_NO_WITHDRAWAL'}
    return value


class InitializedCoupledCisternInputTests(unittest.TestCase):
    def test_source_binding_partition_and_original_preserved(self):
        value = model(shared=True)
        before = deepcopy(value)
        prepared = prepare_initialized_coupling(value)
        raw, metadata = compile(value, prepared.model['network'])
        physical, detail = facilities(raw, value['connectedFacilityDesign'], metadata)
        partition = metadata['catchmentPartition']
        rows = records(raw)[1]
        self.assertEqual(value, before)
        self.assertEqual(partition['preservedPerviousAreaM2'], 4000)
        self.assertAlmostEqual(sum(float(r['tokens'][3])*10000 for r in rows['SUBCATCHMENTS']), 20000)
        self.assertTrue(all(r['tokens'][1] == 'WL_INIT_G421' for r in rows['SUBCATCHMENTS']))
        self.assertEqual(metadata['coupledBinding']['initialization']['warmupSeconds'], 604800)
        self.assertEqual(metadata['coupledBinding']['initialization']['initialDepthAppliesAt'],
                         prepared.summary['network']['startUtc'])
        self.assertEqual(metadata['coupledBinding']['sourceRainfallTriangles'], {'S1': [0, 1]})
        self.assertEqual(detail['sourceCatchmentAssignments'][0]['policy'], 'EXCLUDE_CISTERN_CAPTURE_AND_COVER')
        self.assertIn(b'WLCT_Cistern', physical)
        changed = prepared.model['network'] | {
            'inputText': prepared.model['network']['inputText'].replace('WL_INIT_G421', 'UNBOUND')}
        with self.assertRaisesRegex(FloodModelError, 'INITIALIZATION_BINDING_MISMATCH'):
            compile(value, changed)
        value['connectedCisternDesign']['sourceNetworkSha256'] = '0'*64
        with self.assertRaisesRegex(FloodModelError, 'SOURCE_BINDING_INVALID'):
            compile(value, prepared.model['network'])

    def test_missing_antecedent_and_unsupported_combinations_fail_before_engine(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'tmp') as temporary:
            for kind in ('missing', 'overlap', 'storage', 'pumps', 'basin', 'numerics'):
                value = model(days=28) if kind == 'missing' else model()
                if kind == 'overlap':
                    value['connectedCisternDesign']['captureAreaM2'] = 16000
                keys = {'storage': 'connectedStorageDesign', 'pumps': 'connectedPumpDesign',
                        'basin': 'surfaceBasinDesign', 'numerics': 'networkNumericalProfile'}
                if kind in keys:
                    value[keys[kind]] = {}
                with self.subTest(kind=kind), patch(
                        'waterleague_sim.engine.coupled_flood.EngineProcess') as engine:
                    with self.assertRaises(FloodModelError):
                        run_coupled(value, Path(temporary)/kind)
                    engine.assert_not_called()
            self.assertEqual(list(Path(temporary).iterdir()), [])


class InitializedCoupledCisternNativeTests(unittest.TestCase):
    def test_observed_state_shared_catchment_replay_and_tampering(self):
        target = os.environ.get('INITIALIZED_COUPLED_CISTERN_EVIDENCE_DIR')
        if target:
            root = Path(target).resolve()
            root.mkdir(exist_ok=False, parents=True)
        else:
            temporary = tempfile.TemporaryDirectory(dir=ROOT/'tmp', prefix='initialized-coupled-cistern-')
            self.addCleanup(temporary.cleanup)
            root = Path(temporary.name)
        cases = {'baseline': inputs(None), 'cistern': model(), 'closed-shared': model(shared=True, closed=True),
                 'replay': model()}
        results = {}
        with patch.object(live, 'fetch_range', side_effect=AssertionError('재생 중 외부 조회 금지')):
            for name, source in cases.items():
                path = root/name
                before = deepcopy(source)
                result = results[name] = run_coupled(source, path)
                self.assertEqual(source, before)
                self.assertEqual(result['numericalStatus'], 'PASSED', name)
                self.assertEqual(result['initialization']['evaluationLedger']['numericalStatus'], 'PASSED')
                evaluation_model = source | {'evaluationMetrics': result['evaluationMetrics']['specification']}
                self.assertTrue(read_coupled_record(path, file_digest(path/'coupled-result.json'),
                    context(path, evaluation_model, result))['complete'])
                if name != 'baseline':
                    report = result['connectedCistern']
                    whole = report['wholeRunLedger']['facilities'][0]
                    evaluated = report['evaluationLedger']['facilities'][0]
                    origin = json.loads((path/'evaluation-initial-state.json').read_bytes())['network']
                    self.assertEqual(evaluated['initialStorageM3'], origin['nodes']['WLCT_Cistern']['storageM3'])
                    self.assertGreater(evaluated['initialStorageM3'], 0)
                    self.assertNotAlmostEqual(evaluated['initialStorageM3'], whole['initialStorageM3'], places=6)
                    self.assertGreater(whole['inflowM3'], evaluated['inflowM3'])
                    self.assertEqual(evaluated['floodingM3'], 0)
                    self.assertIsNone(evaluated['reuseM3'])
                    self.assertFalse(report['rankingEligible'])
                    self.assertEqual((report['evaluationLedger']['startSeconds'],
                                      report['evaluationLedger']['endSeconds']), (604800, 626340))
                print(name, result['numericalStatus'], flush=True)
        for key in ('balance', 'evaluationMetrics', 'initialization', 'connectedCistern'):
            self.assertEqual(results['cistern'][key], results['replay'][key])
        for filename in ('network/network.out', 'cistern-network.inp', 'cistern-evaluation-initial.json',
                         'cistern-evaluation-final.json', 'evaluation-initial-state.json'):
            self.assertEqual(file_digest(root/'cistern'/filename), file_digest(root/'replay'/filename))
        self.assertEqual(results['closed-shared']['connectedCistern']['evaluationLedger']['facilities'][0]['drainOperation'],
                         'CLOSED_NO_WITHDRAWAL')
        for name in ('cistern', 'closed-shared'):
            self.assertEqual(results[name]['initialization']['network']['stations'],
                             results['baseline']['initialization']['network']['stations'])
        # 개별 이용조 원장을 다시 해시해도 공통 선행 경계 상태와 다르면 거부한다.
        path = root/'cistern'
        result_path, origin_path = path/'coupled-result.json', path/'cistern-evaluation-initial.json'
        original_result, original_origin = result_path.read_bytes(), origin_path.read_bytes()
        changed_origin = json.loads(original_origin)
        changed_origin['nodes']['WLCT_Cistern']['storageM3'] += .1
        origin_path.write_text(json.dumps(changed_origin))
        changed_result = json.loads(original_result)
        changed_result['files']['cistern-evaluation-initial.json'] = file_digest(origin_path)
        result_path.write_text(json.dumps(changed_result))
        try:
            evaluated_model = cases['cistern'] | {'evaluationMetrics': changed_result['evaluationMetrics']['specification']}
            with self.assertRaisesRegex(EvaluationError, 'CISTERN_INITIALIZATION_STATE_MISMATCH'):
                read_coupled_record(path, file_digest(result_path), context(path, evaluated_model, changed_result))
        finally:
            origin_path.write_bytes(original_origin)
            result_path.write_bytes(original_result)
        report = {
            'classification': 'ARCHIVED_OBSERVED_WEATHER_SYNTHETIC_NETWORK_TERRAIN_NOT_SEOUL',
            'rankingEligible': False, 'productionPublished': False,
            'cases': {name: {'numericalStatus': r['numericalStatus'], 'metrics': r['evaluationMetrics'],
                'initialization': r['initialization'], 'cistern': r.get('connectedCistern')} for name, r in results.items()},
            'sameInputReplay': True, 'originalModelsPreserved': True,
            'rehashTamperedCisternBoundaryRejected': True,
        }
        (root/'verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
