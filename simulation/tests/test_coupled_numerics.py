"""결합 수치 파생의 입력 불변·명시적 설정·재현 검사."""
from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
import unittest

from waterleague_sim.engine.coupled_flood import run_coupled
from waterleague_sim.engine.coupled_numerics import compile
from waterleague_sim.engine.flood_errors import FloodModelError
from waterleague_sim.engine.swmm import ROOT
from waterleague_sim.evaluation.coupled_adapter import file_digest, engine_signature
from waterleague_sim.evaluation.exception import EvaluationError
from waterleague_sim.ingestion.network_variant import derive_compiled, hydraulic_input_hash
from waterleague_sim.ingestion.published_network import digest
from waterleague_sim.reference.coupled_pumps import case, initialized_profile
from simulation.tests.test_storage_composition import check_record

PROFILE = {'id': 'explicit-slot-v1', 'options': {'SURCHARGE_METHOD': 'SLOT',
           'ROUTING_STEP': .005, 'MINIMUM_STEP': .005}}


class CoupledNumericsContractTests(unittest.TestCase):
    def test_same_engine_keeps_comparable_identity_across_design_inputs(self):
        _, metadata = compile(case() | {'networkNumericalProfile': deepcopy(PROFILE)})
        result = {'codeSha256': 'a'*64, 'networkNumericalConfiguration': {'surchargeMethod': 'SLOT'},
                  'networkNumericalProfile': metadata}
        a = engine_signature({'engine': {}}, {'engine': {}}, result)
        changed = deepcopy(result)
        changed['networkNumericalProfile']['profile']['originalSha256'] = 'f'*64
        changed['networkNumericalProfile']['profile']['derivedSha256'] = 'b'*64
        self.assertEqual(a, engine_signature({'engine': {}}, {'engine': {}}, changed))
        changed['networkNumericalConfiguration']['surchargeMethod'] = 'EXTRAN'
        self.assertNotEqual(a, engine_signature({'engine': {}}, {'engine': {}}, changed))

    def test_compiled_network_keeps_physics_and_original_binding(self):
        model = case() | {'networkNumericalProfile': deepcopy(PROFILE)}
        original = deepcopy(model)
        value, metadata = compile(model)
        self.assertEqual(model, original)
        self.assertEqual((value, metadata), compile(model))
        raw, after = [m['network']['inputText'].encode() for m in (model, value)]
        self.assertEqual(hydraulic_input_hash(raw), hydraulic_input_hash(after))
        self.assertEqual(metadata['profile']['originalSha256'], digest(raw))
        self.assertEqual(metadata['profile']['derivedSha256'], digest(after))
        self.assertIsNone(metadata['profile']['reportOutputTransformation'])
        self.assertFalse(metadata['rankingEligible'])
        self.assertEqual(value['connectedPumpDesign'], model['connectedPumpDesign'])

    def test_tolerance_physics_output_path_and_input_injection_rejected(self):
        raw = case()['network']['inputText'].encode()
        for key in ('HEAD_TOLERANCE', 'MIN_SURFAREA', 'START_DATE', 'ALLOW_PONDING', 'FORCE_MAIN_EQUATION'):
            with self.assertRaisesRegex(FloodModelError, 'OPTION_REJECTED'):
                derive_compiled(raw, {'id': 'bad', 'options': {key: 1}})
        for appended in (b'\n[FILES]\nSAVE HOTSTART /tmp/private',
                         b'\n[TIMESERIES]\nSECRET FILE /tmp/private',
                         b'\n[RAINGAGES]\nR VOLUME 0:01 1 FILE /tmp/private',
                         b'\n[LID_USAGE]\nS L 1 1 1 0 0 0 /tmp/private'):
            with self.assertRaisesRegex(FloodModelError, 'EXTERNAL_FILE_REJECTED'):
                derive_compiled(raw+appended, PROFILE)
        with self.assertRaisesRegex(FloodModelError, 'SURCHARGE_INVALID'):
            derive_compiled(raw, {'id': 'bad', 'options': {'SURCHARGE_METHOD': 'SLOT\nALLOW_PONDING YES'}})


class CoupledNumericsNativeTests(unittest.TestCase):
    def root(self, variable='COUPLED_NUMERICS_EVIDENCE_DIR'):
        if target := os.environ.get(variable):
            root = Path(target).resolve()
        else:
            tmp = tempfile.TemporaryDirectory(dir=ROOT/'tmp', prefix='coupled-numerics-')
            self.addCleanup(tmp.cleanup); root = Path(tmp.name)/'runs'
        root.mkdir(parents=True, exist_ok=False)
        return root

    def test_native_profile_and_unchanged_pump_design_chain(self):
        root = self.root()
        model = case() | {'networkNumericalProfile': deepcopy(PROFILE)}
        result = run_coupled(model, root/'profile')
        self.assertEqual(result['numericalStatus'], 'PASSED')
        self.assertTrue(check_record(root/'profile')['complete'])
        self.assertEqual(result['networkNumericalConfiguration']['maximumRoutingStepSeconds'], .005)
        self.assertEqual(result['connectedPumps']['design']['request'], model['connectedPumpDesign'])
        explicit = case(route_step=.005)
        other = run_coupled(explicit, root/'explicit-source')
        self.assertEqual((root/'profile/network/network.out').read_bytes(),
                         (root/'explicit-source/network/network.out').read_bytes())
        self.assertEqual(result['balance'], other['balance'])
        self.assertEqual(result['evaluationMetrics'], other['evaluationMetrics'])
        self.verify_tampering(root/'profile')
        (root/'summary.json').write_text(json.dumps({'classification': 'NUMERICAL_TEST_ONLY',
            'profile': result['networkNumericalProfile'], 'exactOutAndMetrics': True,
            'numericalStatus': result['numericalStatus']}, indent=2)+'\n')

    def test_continuous_initialization_step_and_numerical_area_sensitivity(self):
        root = self.root('COUPLED_NUMERICS_INITIALIZED_EVIDENCE_DIR')
        lids = json.loads((Path(__file__).parent/'fixtures/connected-facilities-v1.json').read_bytes())
        cases = {'default-area': (.05, 0), 'half-step': (.025, 0),
                 'half-area': (.05, 12.566*.3048**2/2)}
        values = {}
        for name, (step, area) in cases.items():
            result = run_coupled(initialized_profile(lids, route_step=step,
                numerical_node_area_m2=area), root/name)
            expected = 'FAILED' if name == 'half-area' else 'PASSED'
            self.assertEqual(result['numericalStatus'], expected, name)
            if name == 'half-area':
                self.assertGreater(result['networkConvergence']['nonConvergedSteps'], 0)
            else:
                self.assertEqual(result['networkConvergence']['nonConvergedSteps'], 0, name)
            record = check_record(root/name)
            self.assertTrue(record['complete'])
            self.assertEqual(record['numericalStatus'], expected)
            self.assertEqual(result['connectedPumps']['operation']['curveStatus'], 'PASSED')
            self.assertEqual(result['connectedPumps']['operation']['evaluation']['pumps'][0]['observedSeconds'], 21540)
            self.assertGreater(result['connectedStorage']['evaluationLedger']['facilities'][0]['initialStorageM3'], 0)
            values[name] = {k: result[k] for k in ('networkNumericalConfiguration', 'networkNumericalProfile',
                'numericalStatus', 'networkConvergence', 'balance', 'connectedPumps')}
            values[name]['rawMetrics'] = result['evaluationMetrics']['raw']
            print(name, result['numericalStatus'], flush=True)
        baseline = values['default-area']
        # 실패한 면적 비교는 원 결과만 보존하고 수렴 비교의 통과 근거에서 제외한다.
        for name in ('half-step',):
            self.assertAlmostEqual(values[name]['rawMetrics']['outwardVolumeM3'],
                baseline['rawMetrics']['outwardVolumeM3'], delta=.1)
            self.assertAlmostEqual(values[name]['rawMetrics']['depthAreaTimeM3Hours'],
                baseline['rawMetrics']['depthAreaTimeM3Hours'], delta=.01)
        (root/'summary.json').write_text(json.dumps({
            'classification': 'OBSERVED_FORCING_SYNTHETIC_DOMAIN_NUMERICAL_SENSITIVITY',
            'siteValidation': False, 'rankingEligible': False, 'cases': values}, indent=2)+'\n')

    def verify_tampering(self, root):
        profile = root/'network-numerical-profile.json'
        result_file = root/'coupled-result.json'
        network_file = root/'network/network-result.json'
        inp = root/'network/network.inp'
        paths = (profile, result_file, network_file, inp)
        originals = [p.read_bytes() for p in paths]
        try:
            value = json.loads(originals[0]); value['profile']['originalSha256'] = '0'*64
            profile.write_text(json.dumps(value))
            result = json.loads(originals[1]); result['networkNumericalProfile'] = value
            result['files']['network-numerical-profile.json'] = file_digest(profile)
            result_file.write_text(json.dumps(result))
            with self.assertRaisesRegex(EvaluationError, 'NUMERICAL_PROFILE_CONTEXT_MISMATCH'):
                check_record(root)
        finally:
            for p, raw in zip(paths, originals): p.write_bytes(raw)
        try:
            network = json.loads(originals[2])
            network['numericalConfiguration']['surchargeMethod'] = 'EXTRAN'
            network_file.write_text(json.dumps(network))
            result = json.loads(originals[1])
            result['networkNumericalConfiguration'] = network['numericalConfiguration']
            result['files']['network/network-result.json'] = file_digest(network_file)
            result_file.write_text(json.dumps(result))
            with self.assertRaisesRegex(EvaluationError, 'NUMERICAL_PROFILE_EFFECTIVE_MISMATCH'):
                check_record(root)
        finally:
            for p, raw in zip(paths, originals): p.write_bytes(raw)
        try:
            inp.write_bytes(originals[3].replace(b'SURCHARGE_METHOD SLOT', b'SURCHARGE_METHOD EXTRAN'))
            network = json.loads(originals[2]); network['files']['network.inp'] = file_digest(inp)
            network_file.write_text(json.dumps(network))
            result = json.loads(originals[1])
            for p in (inp, network_file): result['files'][str(p.relative_to(root))] = file_digest(p)
            result_file.write_text(json.dumps(result))
            with self.assertRaisesRegex(EvaluationError, 'NUMERICAL_PROFILE_NATIVE_MISMATCH'):
                check_record(root)
        finally:
            for p, raw in zip(paths, originals): p.write_bytes(raw)


if __name__ == '__main__': unittest.main()
