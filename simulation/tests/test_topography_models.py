"""새 공간 모델의 원본 연결·과거 기록 보존·실제 엔진 계산 검증."""
import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from shapely.geometry import Polygon, MultiPolygon
from waterleague_sim.engine.swmm import experiment, library_path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts'))
import prepare_topography_models as generator


class TopographyModelTests(unittest.TestCase):
    def test_old_bytes_and_new_model_map_binding(self):
        registry = json.loads((ROOT/'frontend/public/data/maps.json').read_text())
        catalog = json.loads((ROOT/'data/models/catalog.json').read_text())
        expected_models = {e['sha256'] for e in catalog['models']}
        bindings = [h for m in registry['maps'] for h in m['modelHashes']]
        self.assertEqual(set(bindings), expected_models)
        self.assertEqual(len(bindings), len(expected_models))
        for name, sha in zip(generator.LEGACY, generator.LEGACY_HASHES):
            self.assertEqual(generator.sha((ROOT/'data/models'/name).read_bytes()), sha)
        new_map = registry['maps'][1]
        raw = (ROOT/'frontend/public/data'/new_map['file']).read_bytes()
        self.assertEqual(generator.sha(raw), new_map['sha256'])
        snapshot = json.loads(raw)
        buildings = {b['id']: b for b in snapshot['features'] if b['kind'] == 'building'}
        self.assertEqual(len(buildings), 246)
        candidates = json.loads((ROOT/'data/derived/seongsu-topography-candidates-v2.json').read_text())
        for entry in catalog['models'][4:]:
            model = json.loads((ROOT/'data/models'/entry['file']).read_text())
            self.assertEqual(model['mapSnapshotHash'], new_map['sha256'])
            self.assertEqual(model['geometrySourceHash'], snapshot['sourceHash'])
            self.assertEqual(model['geometryModelGeneratorSha256'], generator.audit.digest(Path(generator.__file__)))
            for cell, candidate in zip(model['cells'], candidates['cells']):
                self.assertEqual(cell['coordinates'], candidate['coordinates'])
                self.assertAlmostEqual(Polygon(cell['coordinates']).area, cell['areaM2'], places=6)
                self.assertEqual(cell['siteEligibility'], 'UNKNOWN')
                if cell['kind'] == 'ROOF':
                    b = buildings[cell['buildingId']]
                    self.assertEqual([cell['coordinates']], b['polygons'][0])
                    self.assertEqual(cell['heightM'], b['heightM'])
                else:
                    self.assertEqual(cell['areaM2'], 25)
                    self.assertEqual(cell['maxAreaM2'], 20)
        self.assertIn(catalog['defaultModelHash'], new_map['modelHashes'])

    def test_polygon_holes_multipart_translation_preserves_area(self):
        a = Polygon([(0,0),(10,0),(10,10),(0,10)], [[(2,2),(8,2),(8,8),(2,8)]])
        b = Polygon([(20,0),(22,0),(22,2),(20,2)])
        parts = generator.polygons(MultiPolygon([a,b]), (100,200))
        self.assertEqual(len(parts), 2)
        self.assertEqual(len(parts[0]), 2)
        self.assertAlmostEqual(sum(Polygon(p[0], p[1:]).area for p in parts), 68)

    @unittest.skipUnless(library_path().exists(), 'EPA 엔진 빌드 필요')
    def test_observed_rain_new_geometry_all_facilities_and_reproduction(self):
        catalog = json.loads((ROOT/'data/models/catalog.json').read_text())
        for entry in catalog['models'][4:]:
            model = json.loads((ROOT/'data/models'/entry['file']).read_text())
            placements = [{'cellId': 'R1', 'facilityType': 'GREEN_ROOF', 'areaM2': 100},
                          {'cellId': 'G1', 'facilityType': 'RAIN_GARDEN', 'areaM2': 20},
                          {'cellId': 'G2', 'facilityType': 'PERMEABLE_PAVEMENT', 'areaM2': 20}]
            with self.subTest(model=entry['id']), tempfile.TemporaryDirectory() as tmp:
                result = experiment(model, placements, Path(tmp))
                self.assertEqual(result['validationLevel'], 'EXPLORATORY')
                self.assertFalse(result['official'])
                for name in ('baseline', 'strategy'):
                    self.assertLess(abs(result[name]['runoffContinuityPercent']), 1)
                with tempfile.TemporaryDirectory() as repeat:
                    self.assertEqual(result, experiment(model, placements, Path(repeat)))
