"""시험 전용 조건표로 안전 제약·결측·계산 경계 우회 검증."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from waterleague_sim.spatial.suitability import assess, require_explorable, SiteSuitabilityError
from waterleague_sim.spatial.play_catalog import NativePlayCatalog, NativeCatalogError
from waterleague_sim.placement_validation import cost
from waterleague_sim.engine.continuous import input_source
from waterleague_sim.engine.swmm import SimulationQualityError

ROOT = Path(__file__).resolve().parents[2]
CASES = json.loads((ROOT / 'simulation/tests/fixtures/site-suitability-v1.json').read_bytes())['cases']


class SiteSuitabilityTests(unittest.TestCase):
    def test_common_cases_and_no_inference_from_reference_inputs(self):
        for example in CASES:
            with self.subTest(case=example['id']):
                cell = deepcopy(example['cell'])
                cell['physicalInputs'] = {'slopePercent': 1, 'conductivityMmH': 10, 'soilClass': 'Loam'}
                report = assess(cell)
                self.assertEqual(report['status'], example['expected'])
                self.assertFalse(report['constructionApproved'])
                self.assertEqual(report['explorationAllowed'], example['expected'] in ('UNKNOWN', 'ELIGIBLE'))
                self.assertEqual(report, assess(example['cell']))
                if report['explorationAllowed']:
                    self.assertEqual(require_explorable(cell), report)
                else:
                    with self.assertRaisesRegex(SiteSuitabilityError, '^SITE_SUITABILITY_RESTRICTED$'):
                        require_explorable(cell)

    def test_missing_evidence_invalid_states_and_wrong_scope_are_rejected(self):
        cells = [
            {'kind': 'ROOF', 'siteEligibility': None},
            {'kind': 'ROOF', 'siteEligibility': 'SAFE'},
            {'kind': 'ROOF', 'siteConditions': None},
            {'kind': 'ROOF', 'siteConditions': {'SOIL': {}}},
            {'kind': 'ROOF', 'siteConditions': {'DRAINAGE': None}},
            {'kind': 'ROOF', 'siteConditions': {'DRAINAGE': {'status': 'ELIGIBLE', 'reason': '시험', 'evidence': None}}},
        ]
        for cell in cells:
            with self.assertRaisesRegex(SiteSuitabilityError, '^SITE_SUITABILITY_INVALID$'):
                assess(cell)
        for url in ('http://example.org', 'file:///etc/passwd', 'https://user:secret@example.org', 'https://example.org/\n'):
            cell = deepcopy(CASES[3]['cell'])
            cell['siteConditions']['DRAINAGE']['evidence']['url'] = url
            with self.assertRaisesRegex(SiteSuitabilityError, '^SITE_SUITABILITY_INVALID$'):
                assess(cell)

    def test_catalog_cost_and_engine_boundaries_reject_before_calculation(self):
        placement = {'cellId': 'TEST_ONLY', 'facilityType': 'GREEN_ROOF', 'areaM2': 1}
        model = {'cells': [], 'budget': 100, 'unitCosts': {'GREEN_ROOF': 1}, 'maxPlacements': 1,
                 'rainfall': {'start': '2022-01-01T00:00:00+00:00', 'end': '2022-01-01T00:01:00+00:00',
                              'intervalSeconds': 60, 'depthsMm': [0]}}
        for example in [case for case in CASES if case['expected'] in ('CONDITIONAL', 'PROHIBITED')]:
            cell = {'id': 'TEST_ONLY', 'maxAreaM2': 10, 'allowedTypes': ['GREEN_ROOF'], **example['cell']}
            model['cells'] = [cell]
            reader = object.__new__(NativePlayCatalog)
            with patch.object(reader, 'require', return_value=cell):
                for action in (lambda: reader.placement('TEST_ONLY', 'GREEN_ROOF', 1, district='11110'),
                               lambda: reader.model('TEST_ONLY', district='11110')):
                    with self.assertRaisesRegex(NativeCatalogError, 'SITE_SUITABILITY_RESTRICTED'):
                        action()
            with self.assertRaisesRegex(SiteSuitabilityError, 'SITE_SUITABILITY_RESTRICTED'):
                cost(model, [placement])
            with self.assertRaisesRegex(SimulationQualityError, 'SITE_SUITABILITY_RESTRICTED'):
                input_source(model, [placement], None)
