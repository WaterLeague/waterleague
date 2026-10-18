"""시설·관망·지표 연결과 비개입 관측·실패 전파·원본 재현 검사."""
from copy import deepcopy
from importlib.util import find_spec
import json
import os
from pathlib import Path
import tempfile
import unittest

from waterleague_sim.engine.connected_facilities import compile_design
from waterleague_sim.engine.coupled_facility_network import library_path
from waterleague_sim.engine.coupled_flood import run_coupled
from waterleague_sim.engine.flood_errors import FloodModelError
from waterleague_sim.evaluation.coupled_adapter import engine_signature, file_digest, read_coupled_record
from waterleague_sim.evaluation.exception import EvaluationError
from waterleague_sim.evaluation.values import digest
from waterleague_sim.reference.coupled_facilities import coupled_facility_case
from simulation.tests.test_flood_attribution import policy

ROOT = Path(__file__).resolve().parents[2]
DESIGN = json.loads((Path(__file__).parent / 'fixtures/connected-facilities-v1.json').read_text())


class CoupledFacilityContractTests(unittest.TestCase):
    def test_missing_metrics_and_invalid_design_fail_before_output(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'rejected'
            model = coupled_facility_case(DESIGN)
            model.pop('evaluationMetrics')
            with self.assertRaisesRegex(FloodModelError, 'COUPLED_FACILITY_METRICS_REQUIRED'):
                run_coupled(model, path)
            self.assertFalse(path.exists())
            model = coupled_facility_case(DESIGN)
            model['connectedFacilityDesign'] = None
            with self.assertRaisesRegex(FloodModelError, 'CONNECTED_FACILITY_DESIGN_INVALID'):
                run_coupled(model, path)
            self.assertFalse(path.exists())


@unittest.skipUnless(find_spec('anuga') and library_path().exists(), '시설 결합 엔진 설치 필요')
class CoupledFacilityNativeTests(unittest.TestCase):
    def test_coupled_storage_drainage_metrics_identity_and_failure(self):
        target = os.environ.get('COUPLED_FACILITY_EVIDENCE_DIR')
        if target:
            root = Path(target).resolve()
            self.assertFalse(root.exists())
            root.mkdir(parents=True)
        else:
            temporary = tempfile.TemporaryDirectory(dir=ROOT / 'tmp', prefix='coupled-lid-')
            self.addCleanup(temporary.cleanup)
            root = Path(temporary.name)
        three = deepcopy(DESIGN)
        three['placements'] = [row for row in three['placements'] if row['facilityType'] != 'VEGETATIVE_SWALE']
        baseline = coupled_facility_case(None)
        designed = coupled_facility_case(three)
        original = deepcopy(designed)
        compiled = deepcopy(designed)
        raw, _ = compile_design(compiled['network']['inputText'].encode(), compiled.pop('connectedFacilityDesign'))
        compiled['network']['inputText'] = raw.decode()
        opened = deepcopy(designed)
        next(row for row in opened['connectedFacilityDesign']['placements']
             if row['facilityType'] == 'RAINWATER_CISTERN')['parameters']['drain']['delayHours'] = 0
        cases = {'baseline': baseline, 'facilities': designed, 'legacy-observer': compiled,
                 'frames': designed | {'frameIntervalMilliseconds': 500},
                 'open-cistern': opened, 'failed-swale': coupled_facility_case(DESIGN)}
        results, networks, surfaces = {}, {}, {}
        for name, model in cases.items():
            output = root / name
            result = results[name] = run_coupled(model, output)
            n = networks[name] = json.loads((output / 'network/network-result.json').read_text())
            s = surfaces[name] = json.loads((output / 'surface/surface-result.json').read_text())
            self.assertLess(abs(result['balance']['exchangeCancellationResidualM3']), 1e-10)
            self.assertEqual(n['numericalQuality']['status'], 'PASSED')
            self.assertEqual(s['numericalStatus'], 'PASSED')
            self.assertEqual(result['numericalStatus'], 'FAILED' if name == 'failed-swale' else 'PASSED')
            context = policy()['context'] | {'metricSpecificationSha256': digest(model['evaluationMetrics']),
                'engineSha256': engine_signature(n, s, result)}
            record = read_coupled_record(output, file_digest(output / 'coupled-result.json'), context)
            self.assertEqual(record['numericalStatus'], result['numericalStatus'])
            self.assertFalse(result['evaluationMetrics']['rankingEligible'])
        self.assertEqual(designed, original)
        self.assertEqual(json.loads((root / 'facilities/coupled-input.json').read_text()), original)
        self.assertEqual((root / 'facilities/facility-network.inp').read_bytes(), raw)
        for name in ('legacy-observer', 'frames'):
            self.assertEqual((root / name / 'network/network.out').read_bytes(),
                             (root / 'facilities/network/network.out').read_bytes())
            self.assertEqual(results[name]['balance'], results['facilities']['balance'])
            self.assertEqual(results[name]['evaluationMetrics'], results['facilities']['evaluationMetrics'])
            self.assertEqual(surfaces[name]['final'], surfaces['facilities']['final'])
        self.assertEqual(results['frames']['connectedFacilities'], results['facilities']['connectedFacilities'])
        units = {row['swmmId']: row for row in results['facilities']['connectedFacilities']['final']}
        self.assertEqual(set(units), {'WL_Bioretention', 'WL_Trench', 'WL_Cistern'})
        self.assertGreater(units['WL_Trench']['infiltrationM3'], 0)
        self.assertGreater(units['WL_Cistern']['surfaceOutflowM3'], 0)
        self.assertEqual(units['WL_Cistern']['drainOutflowM3'], 0)
        self.assertAlmostEqual(units['WL_Cistern']['finalStorageM3'], .02, places=12)
        open_unit = next(row for row in results['open-cistern']['connectedFacilities']['final']
                         if row['swmmId'] == 'WL_Cistern')
        self.assertGreater(open_unit['drainOutflowM3'], 0)
        self.assertLess(open_unit['surfaceOutflowM3'], units['WL_Cistern']['surfaceOutflowM3'])
        self.assertLess(results['facilities']['evaluationMetrics']['raw']['outwardVolumeM3'],
                        results['baseline']['evaluationMetrics']['raw']['outwardVolumeM3'])
        frames = [json.loads(row) for row in (root / 'frames/network-frames.jsonl').read_text().splitlines()]
        self.assertTrue(any(row['facilities'][0]['hydrologyTimeSeconds'] != row['totals']['timeSeconds'] for row in frames))
        failed = results['failed-swale']
        self.assertEqual(failed['connectedFacilities']['quality']['failedFacilityIds'], ['WL_Swale'])
        self.assertEqual(failed['evaluationMetrics']['status'], 'FAILED_DIAGNOSTIC')
        self.assertGreater(failed['evaluationMetrics']['raw']['depthAreaTimeM3Hours'], 0)
        detail = results['facilities']['connectedFacilities']
        self.assertFalse(detail['routingSurfaceBalanceAddsFacilityOutflows'])
        self.assertFalse(detail['routingSurfaceBalanceIncludesFacilityStorage'])
        # 상위 해시를 새로 제공해도 내부 시설 상태와 어긋난 요약은 수용하지 않는다.
        altered = deepcopy(results['facilities'])
        altered['connectedFacilities']['final'][0]['finalStorageM3'] += 1
        path = root / 'facilities/coupled-result.json'
        original_bytes = path.read_bytes()
        try:
            path.write_text(json.dumps(altered))
            context = policy()['context'] | {'metricSpecificationSha256': digest(designed['evaluationMetrics']),
                'engineSha256': engine_signature(networks['facilities'], surfaces['facilities'], altered)}
            with self.assertRaisesRegex(EvaluationError, 'FACILITY_CONTEXT_MISMATCH'):
                read_coupled_record(path.parent, file_digest(path), context)
        finally:
            path.write_bytes(original_bytes)
        summary = {'classification': 'NUMERICAL_COUPLING_NOT_SEOUL_VALIDATION',
            'cases': {name: {key: result[key] for key in
                ('numericalStatus', 'balance', 'evaluationMetrics')} for name, result in results.items()},
            'failedFacilityQuality': failed['connectedFacilities']['quality'],
            'observerBinaryUnchanged': True, 'displayFramesPhysicsUnchanged': True}
        (root / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    unittest.main()
