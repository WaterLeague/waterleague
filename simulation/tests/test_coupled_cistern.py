"""실제 강우 응답·합성 관망/지표의 이용조 결합과 중복 집수·변조 검사."""
from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from waterleague_sim.engine.coupled_flood import run_coupled
from waterleague_sim.engine.flood_errors import FloodModelError
from waterleague_sim.evaluation.coupled_adapter import read_coupled_record, file_digest
from waterleague_sim.evaluation.exception import EvaluationError
from waterleague_sim.ingestion import live
from waterleague_sim.ingestion.published_network import digest
from waterleague_sim.reference.cistern_network import design
from waterleague_sim.reference.coupled_facilities import coupled_facility_case
from simulation.tests.test_live_coupled_facilities import designed, context
from simulation.tests.test_live_network_rainfall import case
from run_live_surface import execute

ROOT = Path(__file__).resolve().parents[2]


def model(*, shared=False, closed=False, partial=False, pipes=False, dry_network=False):
    value = designed(('BIORETENTION',)) if shared else case()
    if dry_network:
        value['network']['inputText'] = value['network']['inputText'].replace('TANK 0 5 2.0', 'TANK 0 5 0')
    spec = design(value['network']['inputText'].encode())
    if shared:
        spec['schemaVersion'] = 3
    if closed:
        spec['drain'] = {'mode': 'CLOSED_NO_WITHDRAWAL'}
    if partial:
        spec['initialDepthM'] = .3
    if pipes:
        pipe = {'lengthM': 10., 'diameterM': .1, 'roughness': .013, 'upstreamInvertM': 0.,
                'upstreamMaxDepthM': 3., 'downstreamInvertM': 0.}
        for kind in ('inletPipe', 'drainPipe', 'overflowPipe'):
            spec[kind] = deepcopy(pipe)
    value['connectedCisternDesign'] = spec
    return value


class CoupledCisternTests(unittest.TestCase):
    def test_invalid_design_rejected_before_observation_fetch(self):
        with tempfile.TemporaryDirectory() as temporary:
            for mode in ('source', 'overlap', 'shared', 'lid-overlap', 'missing-metrics', 'composition'):
                value = model(shared=mode in ('shared', 'lid-overlap'))
                if mode == 'source':
                    value['connectedCisternDesign']['sourceNetworkSha256'] = '0'*64
                if mode == 'overlap':
                    value['connectedCisternDesign']['captureAreaM2'] = 100
                if mode == 'shared':
                    value['connectedCisternDesign']['schemaVersion'] = 1
                if mode == 'lid-overlap':
                    value['connectedFacilityDesign']['placements'][0]['treatedImperviousM2'] = 80
                if mode == 'missing-metrics':
                    value.pop('evaluationMetrics')
                if mode == 'composition':
                    value['connectedStorageDesign'] = {}
                specification = value.pop('observedRainfall')
                rainfall = {k: specification[k] for k in
                    ('startUtc', 'endUtc', 'stationByTriangle', 'stationByCatchment', 'assignmentEvidence')}
                with self.subTest(mode=mode), patch.object(live, 'observed_forcing') as fetch:
                    with self.assertRaises(FloodModelError):
                        execute({'mode': 'coupled', 'model': value, 'rainfall': rainfall},
                                Path(temporary)/mode, 'secret')
                    fetch.assert_not_called()
            self.assertEqual(list(Path(temporary).iterdir()), [])

    def test_coupled_replay_window_storage_and_readback(self):
        target = os.environ.get('COUPLED_CISTERN_EVIDENCE_DIR')
        if target:
            root = Path(target).resolve()
            root.mkdir(exist_ok=False, parents=True)
        else:
            temporary = tempfile.TemporaryDirectory(dir=ROOT/'tmp', prefix='coupled-cistern-')
            self.addCleanup(temporary.cleanup)
            root = Path(temporary.name)
        ordinary = model()
        window = model(closed=True, partial=True)
        window['evaluationMetrics'].update(startMilliseconds=30000, endMilliseconds=90000)
        mixed = model(shared=True)
        mixed['network']['inputText'] = mixed['network']['inputText'].replace('0.01 100 10', '0.01 80 10')
        mixed['connectedCisternDesign']['sourceNetworkSha256'] = digest(mixed['network']['inputText'].encode())
        synthetic = coupled_facility_case(None)
        synthetic['connectedCisternDesign'] = design(synthetic['network']['inputText'].encode())
        cases = {'baseline': case(), 'cistern': ordinary, 'replay': deepcopy(ordinary),
                 'shared': model(shared=True), 'closed-window': window,
                 'pipes-dry-network': model(pipes=True, dry_network=True),
                 'mixed-shared': mixed, 'synthetic-rain': synthetic}
        results = {}
        with patch.object(live, 'fetch_range', side_effect=AssertionError('재생 중 외부 조회 금지')):
            for name, source in cases.items():
                before = deepcopy(source)
                path = root/name
                result = results[name] = run_coupled(source, path)
                self.assertEqual(source, before)
                record = read_coupled_record(path, file_digest(path/'coupled-result.json'),
                                             context(path, source, result))
                self.assertEqual(record['numericalStatus'], result['numericalStatus'])
                self.assertEqual(result['numericalStatus'],
                    'FAILED' if name == 'pipes-dry-network' else 'PASSED', name)
                if name == 'pipes-dry-network':
                    self.assertIn('ROUTING_VOLUME_RESIDUAL_EXCEEDED',
                                  result['networkNumericalQuality']['failureReasons'])
                    self.assertEqual(result['connectedCistern']['numericalStatus'], 'FAILED')
                self.assertLess(abs(result['balance']['exchangeCancellationResidualM3']), 1e-8)
                if 'networkRainfall' in result:
                    self.assertLess(abs(result['networkRainfall']['nativeVolumeResidualM3']), 1e-8)
                if name != 'baseline':
                    ledger = result['connectedCistern']['wholeRunLedger']['facilities'][0]
                    self.assertIsNone(ledger['reuseM3'])
                    self.assertEqual(result['connectedCistern']['rankingEligible'], False)
                    self.assertGreater(ledger['inflowM3'], 0)
        for key in ('connectedCistern', 'balance', 'evaluationMetrics'):
            self.assertEqual(results['cistern'][key], results['replay'][key])
        self.assertEqual((root/'cistern/network/network.out').read_bytes(),
                         (root/'replay/network/network.out').read_bytes())
        for key in ('expectedNetworkRainfallM3', 'catchmentAreasM2', 'stations', 'nativeInput'):
            self.assertEqual(results['baseline']['networkRainfall'][key], results['cistern']['networkRainfall'][key])
        self.assertAlmostEqual(results['baseline']['networkRainfall']['appliedCombinedRainfallM3'],
                               results['cistern']['networkRainfall']['appliedCombinedRainfallM3'], delta=1e-8)
        period = results['closed-window']['connectedCistern']['evaluationLedger']
        self.assertEqual((period['startSeconds'], period['endSeconds']), (30, 90))
        self.assertEqual(period['facilities'][0]['drainOperation'], 'CLOSED_NO_WITHDRAWAL')
        shared = results['shared']['connectedFacilities']['design']
        self.assertEqual(shared['sourceCatchmentAssignments'][0]['policy'], 'EXCLUDE_CISTERN_CAPTURE_AND_COVER')
        # 응답 해시를 다시 계산하더라도 원장만 바꾼 결과는 네이티브 상태와 대조해 거부한다.
        path = root/'cistern/coupled-result.json'
        original = path.read_bytes()
        changed = json.loads(original)
        changed['connectedCistern']['wholeRunLedger']['facilities'][0]['finalStorageM3'] += 1
        path.write_text(json.dumps(changed))
        with self.assertRaisesRegex(EvaluationError, 'CISTERN_LEDGER_MISMATCH'):
            read_coupled_record(path.parent, file_digest(path), context(path.parent, ordinary, changed))
        path.write_bytes(original)
        native_path, network_path = root/'cistern/network/network.inp', root/'cistern/network/network-result.json'
        native_raw, network_raw = native_path.read_bytes(), network_path.read_bytes()
        changed = json.loads(original)
        native_path.write_bytes(native_raw.replace(b'WLCT_Cistern_C WL_AWS_G401', b'WLCT_Cistern_C G'))
        self.assertNotEqual(native_path.read_bytes(), native_raw)
        network = json.loads(network_raw)
        network['files']['network.inp'] = file_digest(native_path)
        network_path.write_text(json.dumps(network))
        for relative in ('network/network.inp', 'network/network-result.json'):
            changed['files'][relative] = file_digest(root/'cistern'/relative)
        path.write_text(json.dumps(changed))
        with self.assertRaisesRegex(EvaluationError, 'RAIN_INPUT_MISMATCH'):
            read_coupled_record(path.parent, file_digest(path), context(path.parent, ordinary, changed))
        path.write_bytes(original)
        native_path.write_bytes(native_raw)
        network_path.write_bytes(network_raw)
        report = {
            'classification': 'SYNTHETIC_NETWORK_TERRAIN_WITH_ARCHIVED_OR_EXPLICIT_TEST_RAIN_NOT_SEOUL',
            'cases': {name: {'numericalStatus': result['numericalStatus'], 'balance': result['balance'],
                'cistern': result.get('connectedCistern'),
                'metrics': result['evaluationMetrics']['raw']} for name, result in results.items()},
            'sameInputReplay': True, 'originalModelsPreserved': True,
            'productionPublished': False, 'rankingEligible': False,
        }
        (root/'verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')

    def test_unmapped_tank_overflow_remains_failure(self):
        value = model(closed=True)
        spec = value['connectedCisternDesign']
        spec['initialDepthM'] = 1.4
        spec['overflow']['diameterM'] = .001
        with tempfile.TemporaryDirectory(dir=ROOT/'tmp') as temporary:
            for name, source in (('overflow', value), ('pipe-backpressure', model(pipes=True))):
                path = Path(temporary)/name
                with self.subTest(name=name), self.assertRaisesRegex(FloodModelError, 'COUPLED_UNMAPPED_NODE_FLOODING'):
                    run_coupled(source, path)
                self.assertFalse((path/'coupled-result.json').exists())
                failure = json.loads((path/'coupled-failure.json').read_text())
                self.assertEqual(failure['code'], 'COUPLED_UNMAPPED_NODE_FLOODING')
