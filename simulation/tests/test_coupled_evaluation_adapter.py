"""고정 결과 해시·중첩 원장·원 지표 불일치와 경로 탈출 검사."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from waterleague_sim.evaluation.coupled_adapter import engine_signature, file_digest, read_coupled_record
from waterleague_sim.evaluation.exception import EvaluationError
from waterleague_sim.evaluation.values import digest
from simulation.tests.test_flood_attribution import policy


class CoupledEvaluationAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / 'network').mkdir()
        (self.root / 'surface').mkdir()
        (self.root / 'network/network.rpt').write_text('closed report fixture')
        self.spec = {'evidence': 'NUMERICAL_HASH_TEST_ONLY'}
        spec_hash = digest(self.spec)
        self.network = {'engine': {'fixture': 'network'}, 'numericalConfiguration': {},
            'numericalStatus': 'PASSED', 'complete': True,
            'evaluationMetrics': {'specificationSha256': spec_hash, 'complete': True,
                                  'combined': {'outwardVolumeM3': 2, 'peakOutwardM3s': .1}},
            'files': {'network.rpt': file_digest(self.root / 'network/network.rpt')}}
        self.surface = {'engine': {'fixture': 'surface'}, 'numericalStatus': 'PASSED',
            'evaluationMetrics': {'specificationSha256': spec_hash, 'complete': True, 'depthAreaTimeM3Hours': .01},
            'files': {}}
        self.model = {'evaluationMetrics': self.spec, 'evidence': 'NUMERICAL_TEST_ONLY'}
        self.result = {'codeSha256': digest('fixture code'), 'networkNumericalConfiguration': {},
            'numericalStatus': 'PASSED', 'evaluationMetrics': {'specification': self.spec,
                'specificationSha256': spec_hash, 'complete': True,
                'raw': {'outwardVolumeM3': 2, 'peakOutwardM3s': .1, 'depthAreaTimeM3Hours': .01}}}
        self.context = policy()['context'] | {'metricSpecificationSha256': spec_hash,
            'engineSha256': engine_signature(self.network, self.surface, self.result)}
        self.refresh()

    def refresh(self):
        for relative, value in (('coupled-input.json', self.model), ('network/network-result.json', self.network),
                                ('surface/surface-result.json', self.surface)):
            (self.root / relative).write_text(json.dumps(value))
        self.result['files'] = {str(p.relative_to(self.root)): file_digest(p)
            for p in self.root.rglob('*') if p.is_file() and p.name != 'coupled-result.json'}
        self.write_result()

    def write_result(self):
        (self.root / 'coupled-result.json').write_text(json.dumps(self.result))
        self.expected = file_digest(self.root / 'coupled-result.json')

    def read(self):
        return read_coupled_record(self.root, self.expected, self.context)

    def add_surface_quality(self):
        self.model.update(surface={'schemaVersion': 2}, durationSeconds=120)
        self.surface['numericalConfiguration'] = {'policyVersion': 'ANUGA_DE0_INSCRIBED_RADIUS_v2',
                                                  'configuredMaximumStepSeconds': 30}
        self.result['surfaceNumericalConfiguration'] = deepcopy(self.surface['numericalConfiguration'])
        self.surface['engine']['qualityAdapterSha256'] = digest('quality observer')
        quality = {'policyVersion': 'SURFACE_NATIVE_BALANCE_v1', 'status': 'PASSED', 'failureCode': None,
                   'sourceSha256': self.surface['engine']['qualityAdapterSha256'],
                   'lastInternalTimeSeconds': 120}
        self.surface['numericalQuality'] = quality
        self.result['surfaceNumericalQuality'] = deepcopy(quality)
        path = self.root / 'surface/surface-quality.json'
        path.write_text(json.dumps(quality))
        self.surface['files']['surface-quality.json'] = file_digest(path)
        self.context['engineSha256'] = engine_signature(self.network, self.surface, self.result)
        self.refresh()

    def test_surface_numerical_policy_is_bound_to_engine_context(self):
        previous = self.context['engineSha256']
        self.add_surface_quality()
        self.assertNotEqual(previous, self.context['engineSha256'])
        self.assertTrue(self.read()['complete'])
        self.result['surfaceNumericalConfiguration']['configuredMaximumStepSeconds'] = 1
        self.refresh()
        with self.assertRaisesRegex(EvaluationError, 'CONTEXT_MISMATCH'):
            self.read()
        self.surface['numericalConfiguration']['configuredMaximumStepSeconds'] = 1
        self.refresh()
        with self.assertRaisesRegex(EvaluationError, 'CONTEXT_MISMATCH'):
            self.read()

    def test_version_two_requires_quality_artifact_and_matching_observer(self):
        self.add_surface_quality()
        saved = self.surface.pop('numericalQuality')
        self.refresh()
        with self.assertRaisesRegex(EvaluationError, 'SURFACE_QUALITY_MISMATCH'):
            self.read()
        self.surface['numericalQuality'] = saved
        self.surface['engine']['qualityAdapterSha256'] = digest('different observer')
        self.context['engineSha256'] = engine_signature(self.network, self.surface, self.result)
        self.refresh()
        with self.assertRaisesRegex(EvaluationError, 'SURFACE_QUALITY_MISMATCH'):
            self.read()

    def test_failed_or_incomplete_quality_cannot_be_promoted_to_passed(self):
        self.add_surface_quality()
        for change, code in (({'status': 'FAILED'}, 'ENGINE_STATUS_MISMATCH'),
                             ({'lastInternalTimeSeconds': 119}, 'SURFACE_TIME_MISMATCH')):
            original = deepcopy(self.surface['numericalQuality'])
            quality = self.surface['numericalQuality'] | change
            self.surface['numericalQuality'] = self.result['surfaceNumericalQuality'] = quality
            path = self.root / 'surface/surface-quality.json'
            path.write_text(json.dumps(quality))
            self.surface['files']['surface-quality.json'] = file_digest(path)
            self.refresh()
            with self.assertRaisesRegex(EvaluationError, code):
                self.read()
            self.surface['numericalQuality'] = original

    def test_verified_raw_values_and_engine_policy_binding(self):
        record = self.read()
        self.assertEqual(record['raw'], self.result['evaluationMetrics']['raw'])
        self.assertEqual(record['resultSha256'], self.expected)
        self.context['engineSha256'] = digest('other engine')
        with self.assertRaisesRegex(EvaluationError, 'CONTEXT_MISMATCH'):
            self.read()

    def test_result_and_report_tampering_rejected(self):
        (self.root / 'coupled-result.json').write_text('{}')
        with self.assertRaisesRegex(EvaluationError, 'RESULT_HASH_MISMATCH'):
            self.read()
        self.write_result()
        (self.root / 'network/network.rpt').write_text('changed after manifest')
        with self.assertRaisesRegex(EvaluationError, 'ARTIFACT_HASH_MISMATCH'):
            self.read()

    def test_nested_manifest_checked_even_when_outer_hashes_match(self):
        self.network['files']['network.rpt'] = '0' * 64
        self.refresh()
        with self.assertRaisesRegex(EvaluationError, 'ARTIFACT_HASH_MISMATCH'):
            self.read()

    def test_traversal_and_symlink_rejected(self):
        self.result['files']['../outside'] = '0' * 64
        self.write_result()
        with self.assertRaisesRegex(EvaluationError, 'PATH_INVALID'):
            self.read()
        self.result['files'].pop('../outside')
        link = self.root / 'network/report-link'
        link.symlink_to(self.root / 'network/network.rpt')
        self.result['files']['network/report-link'] = file_digest(link)
        self.write_result()
        with self.assertRaisesRegex(EvaluationError, 'PATH_INVALID'):
            self.read()

    def test_outer_raw_metrics_cannot_disagree_with_engine_outputs(self):
        self.result['evaluationMetrics']['raw']['outwardVolumeM3'] = 100
        self.write_result()
        with self.assertRaisesRegex(EvaluationError, 'RAW_METRICS_MISMATCH'):
            self.read()

    def test_duplicate_keys_and_numerical_evidence_promotion_rejected(self):
        path = self.root / 'network/network-result.json'
        path.write_text('{"engine":{},"engine":{}}')
        self.result['files']['network/network-result.json'] = file_digest(path)
        self.write_result()
        with self.assertRaisesRegex(EvaluationError, 'DUPLICATE_KEY'):
            self.read()
        self.refresh()
        self.context['evidenceClass'] = 'PUBLIC_DATA'
        with self.assertRaisesRegex(EvaluationError, 'EVIDENCE_MISMATCH'):
            self.read()


if __name__ == '__main__':
    unittest.main()
