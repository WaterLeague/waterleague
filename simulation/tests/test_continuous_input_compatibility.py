"""연속 시설 확장이 등록 모델의 생성기·수치 입력을 변경하지 않는지 검사."""
import hashlib
import json
from pathlib import Path
import unittest

from waterleague_sim import shared_model
from waterleague_sim.engine import continuous, swmm
from waterleague_sim.model_catalog import read_catalog

ROOT = Path(__file__).resolve().parents[2]


class ContinuousInputCompatibilityTests(unittest.TestCase):
    def test_registered_models_match_their_frozen_generator(self):
        generator = hashlib.sha256(Path(swmm.__file__).read_bytes()).hexdigest()
        for raw in read_catalog(ROOT / 'data/models').values():
            self.assertEqual(json.loads(raw)['generatorSha256'], generator)

    def test_six_facility_inputs_preserve_exact_bytes(self):
        fixture = json.loads((Path(__file__).parent / 'fixtures/continuous-inputs-v1.json').read_text())
        for case in fixture['cases']:
            with self.subTest(facility=case['placement']['facilityType']):
                district, version = case['districtId'], case['siteVersion']
                model, _, _ = shared_model.resolve({'district_id': district,
                    'cell_id': case['placement']['cellId'],
                    'model_hash': shared_model.site_catalog(version)[district]['sha256']})
                model['rainfall'] = case['rainfall']
                source = continuous.input_source(model, [case['placement']], None)
                self.assertEqual(case['inputSha256'], hashlib.sha256(source.encode()).hexdigest())
