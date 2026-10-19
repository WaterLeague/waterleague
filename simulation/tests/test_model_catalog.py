"""배포 입력의 경로·해시·등록 조건 훼손 거부."""
import unittest
import tempfile
import shutil
import json
from pathlib import Path
from waterleague_sim.model_catalog import read_catalog
ROOT = Path(__file__).resolve().parents[2]


class ModelCatalogTests(unittest.TestCase):
    def test_registered_models_have_distinct_rainfall_and_unchanged_geometry(self):
        catalog = read_catalog(ROOT/'data/models')
        models = [json.loads(data) for data in catalog.values()]
        regions = json.loads((ROOT/'data/manifests/seoul-play-v2.json').read_text())['regions']
        events = json.loads((ROOT/'backend/src/main/resources/disasters/seoul-events-v1.json').read_text())['events']
        expected_by_map = {r['mapId']: set(r['modelHashes']) for r in regions}
        for event in events:
            self.assertEqual(25, len(event['models']))
            for model in event['models']:
                expected_by_map['seoul-osm-v1-' + model['districtId']].add(model['modelHash'])
        actual_by_map = {}
        for model_hash, raw in catalog.items():
            actual_by_map.setdefault(json.loads(raw).get('mapId', 'legacy'), set()).add(model_hash)
        self.assertEqual(set(expected_by_map), {key for key in actual_by_map if key.startswith('seoul-osm-v1-')})
        for map_id, expected_hashes in expected_by_map.items():
            self.assertEqual(expected_hashes, actual_by_map[map_id])
        self.assertTrue({18.5, 55.0, 104.0, 109.7}.issubset({m['rainfall']['totalDepthMm'] for m in models}))
        families = {}
        for m in models:
            families.setdefault(m.get('mapId', 'legacy'), []).append(m)
        self.assertEqual(27, len(families))
        for map_id, family in families.items():
            expected = len(expected_by_map[map_id]) if map_id.startswith('seoul-osm-v1-') else 4
            self.assertEqual(expected, len(family))
            self.assertTrue(all(m['cells'] == family[0]['cells'] for m in family))

    def test_modified_source_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(ROOT/'data/models', root, dirs_exist_ok=True)
            (root/'seongsu-lab.json').write_text('{}')
            with self.assertRaisesRegex(ValueError, '해시'):
                read_catalog(root)

    def test_traversal_and_duplicate_and_missing_default_are_rejected(self):
        for mutation in ('path', 'duplicate', 'default'):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                shutil.copytree(ROOT/'data/models', root, dirs_exist_ok=True)
                path = root/'catalog.json'
                data = json.loads(path.read_text())
                if mutation == 'path': data['models'][0]['file'] = '../seongsu-lab.json'
                elif mutation == 'duplicate': data['models'].append(data['models'][0])
                else: data['defaultModelHash'] = '0'*64
                path.write_text(json.dumps(data))
                with self.assertRaises(ValueError): read_catalog(root)
