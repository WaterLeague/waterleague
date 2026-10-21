"""공개 원본 결속과 시설 대안의 같은 관측기·실제 입력·변조 거부 검사."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from test_published_surface_connection import request
from test_connected_facilities import FIXTURE
from test_flood_attribution import policy
from waterleague_sim.engine.published_surface_connection import compile_connection, FACILITY_OBSERVER
from waterleague_sim.engine.coupled_flood import run_coupled, _validate
from waterleague_sim.engine.connected_facilities import compile_design
from waterleague_sim.engine.coupled_numerics import compile as numerical
from waterleague_sim.engine.flood_errors import FloodModelError
from waterleague_sim.evaluation.coupled_adapter import read_coupled_record, engine_signature, file_digest
from waterleague_sim.evaluation.exception import EvaluationError
from waterleague_sim.evaluation.values import digest


def model(design=True, hydrology=False):
    source = request()
    if hydrology:
        source['parameters']['networkNumericalProfile']['options'].update(WET_STEP=1, DRY_STEP=1)
    value = compile_connection(source)
    value['networkObserverPolicy'] = FACILITY_OBSERVER
    if design:
        placements = deepcopy(FIXTURE['placements'][:3])
        for p in placements:
            p.update(subcatchmentId='S', areaM2=10., replacedImperviousM2=10., treatedImperviousM2=10.)
        value['connectedFacilityDesign'] = FIXTURE | {'placements': placements}
    return value


class PublicSurfaceFacilityTests(unittest.TestCase):
    def test_hydrology_profile_reads_native_effective_steps_and_rejects_rehashed_changes(self):
        value = model(hydrology=True)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            result = run_coupled(value, root/'case')
            target = root/'case'
            network_file = target/'network/network-result.json'
            result_file = target/'coupled-result.json'
            network = json.loads(network_file.read_bytes())
            surface = json.loads((target/'surface/surface-result.json').read_bytes())
            configuration = network['numericalConfiguration']
            self.assertEqual(configuration['wetRunoffStepSeconds'], 1)
            self.assertEqual(configuration['dryRunoffStepSeconds'], 1)
            self.assertEqual(configuration['declaredInputOptions']['WET_STEP'], '00:00:01')
            def read_record():
                context = policy()['context'] | {'engineSha256': engine_signature(network, surface, result),
                    'metricSpecificationSha256': digest(value['evaluationMetrics'])}
                return read_coupled_record(target, file_digest(result_file), context)
            self.assertTrue(read_record()['complete'])
            for field in ('wetRunoffStepSeconds', 'dryRunoffStepSeconds'):
                changed = deepcopy(configuration)
                changed[field] = 2
                network['numericalConfiguration'] = result['networkNumericalConfiguration'] = changed
                network_file.write_text(json.dumps(network))
                result['files']['network/network-result.json'] = file_digest(network_file)
                result_file.write_text(json.dumps(result))
                with self.assertRaisesRegex(EvaluationError, 'NUMERICAL_PROFILE_EFFECTIVE_MISMATCH'):
                    read_record()

    def test_versioned_public_profile_refines_both_cases_without_changing_facilities(self):
        from waterleague_sim.watershed_surface import verify, models, PROFILE_SHA256
        from waterleague_sim.run_watershed_job import inputs, CATALOG_HASH
        from waterleague_sim.ingestion.published_network import digest as raw_digest
        from waterleague_sim.ingestion.network_variant import hydraulic_input_hash
        design = json.loads((Path(__file__).parent/'fixtures/seocho-three-lid-design-v1.json').read_bytes())
        self.assertEqual(verify(design)['id'], 'seocho-surface-design-v1')
        def prepare(value):
            raw = json.dumps(value)
            return inputs({'modelHash': CATALOG_HASH, 'placements': raw,
                           'inputHash': raw_digest((CATALOG_HASH+'\n'+raw).encode())})
        old = prepare(design)
        refined = deepcopy(design)
        refined['surfaceConnection'] = {'id': 'seocho-surface-design-v2', 'profileSha256': PROFILE_SHA256}
        new = prepare(refined)
        for index in (2, 3):
            self.assertIn(b'00:00:01', new[index])
            self.assertNotEqual(old[index], new[index])
            self.assertEqual(hydraulic_input_hash(old[index], hydrology=True),
                             hydraulic_input_hash(new[index], hydrology=True))
        for key in old[5]:
            if key not in ('originalSha256', 'derivedSha256'):
                self.assertEqual(old[5][key], new[5][key])
        profile, baseline, strategy = models(refined)
        for value in (baseline, strategy):
            compiled, _ = numerical(value)
            self.assertIn('WET_STEP', compiled['network']['inputText'])
            self.assertEqual(value['networkNumericalProfile']['options']['WET_STEP'], 1)
        self.assertEqual(strategy['connectedFacilityDesign']['placements'], design['placements'])
        refined['surfaceConnection']['id'] = 'seocho-surface-design-v1'
        with self.assertRaisesRegex(FloodModelError, 'DESIGN_INVALID'):
            verify(refined)

    def test_empty_facility_observer_preserves_native_baseline(self):
        observed = model(False)
        plain = deepcopy(observed)
        plain.pop('networkObserverPolicy')
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            a = run_coupled(plain, root/'plain')
            b = run_coupled(observed, root/'observed')
            self.assertEqual(a['balance'], b['balance'])
            self.assertEqual(a['evaluationMetrics'], b['evaluationMetrics'])
            self.assertEqual((root/'plain/network/network.out').read_bytes(),
                             (root/'observed/network/network.out').read_bytes())

    def test_excess_capture_and_unbound_observers_rejected(self):
        value = model()
        value['connectedFacilityDesign']['placements'][0]['treatedImperviousM2'] = 100
        with self.assertRaisesRegex(FloodModelError, 'CAPTURE_AREA_EXCEEDED'):
            _validate(value)
        value = model(False)
        value['networkObserverPolicy'] = 'UNVERIFIED'
        with self.assertRaisesRegex(FloodModelError, 'OBSERVER_POLICY_INVALID'):
            _validate(value)
        value = model()
        value['surface']['rainfallPartition']['surfaceFractions'][0] = .123
        with self.assertRaisesRegex(FloodModelError, 'BINDING_MISMATCH'):
            _validate(value)

    def test_native_design_common_engine_and_rehashed_facility_tampering(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cases = {'baseline': model(False), 'design': model()}
            contexts = []
            results = []
            for name, value in cases.items():
                target = root/name
                result = run_coupled(value, target)
                network = json.loads((target/'network/network-result.json').read_bytes())
                surface = json.loads((target/'surface/surface-result.json').read_bytes())
                context = policy()['context'] | {'engineSha256': engine_signature(network, surface, result),
                    'metricSpecificationSha256': digest(value['evaluationMetrics'])}
                record = read_coupled_record(target, file_digest(target/'coupled-result.json'), context)
                self.assertTrue(record['complete'])
                self.assertEqual(network['engine']['facilityObserverVersion'], 1)
                self.assertLess(abs(result['balance']['exchangeCancellationResidualM3']), 1e-8)
                contexts.append(context)
                results.append(result)
            self.assertEqual(contexts[0], contexts[1])
            self.assertNotEqual(results[0]['balance']['networkToSurfaceM3'], results[1]['balance']['networkToSurfaceM3'])
            original, _ = numerical(cases['design'])
            raw, _ = compile_design(original['network']['inputText'].encode(), cases['design']['connectedFacilityDesign'])
            self.assertEqual((root/'design/network/network.inp').read_bytes(), raw)
            result = results[1]
            target = root/'design'
            network = json.loads((target/'network/network-result.json').read_bytes())
            path = target/'network/network.inp'
            path.write_bytes(path.read_bytes().replace(b'WL_Bioretention SURFACE 152.4', b'WL_Bioretention SURFACE 153.4'))
            self.assertNotEqual(path.read_bytes(), raw)
            network['files']['network.inp'] = file_digest(path)
            (target/'network/network-result.json').write_text(json.dumps(network))
            for name in ('network/network.inp', 'network/network-result.json'):
                result['files'][name] = file_digest(target/name)
            (target/'coupled-result.json').write_text(json.dumps(result))
            with self.assertRaisesRegex(EvaluationError, 'PUBLIC_CONNECTION_NATIVE_MISMATCH'):
                read_coupled_record(target, file_digest(target/'coupled-result.json'), contexts[1])


if __name__ == '__main__':
    unittest.main()
