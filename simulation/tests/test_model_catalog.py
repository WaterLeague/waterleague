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
        models = [json.loads(data) for data in read_catalog(ROOT/'data/models').values()]
        self.assertEqual(4, len(models))
        self.assertEqual({18.5, 55.0, 104.0, 109.7}, {m['rainfall']['totalDepthMm'] for m in models})
        self.assertTrue(all(m['cells'] == models[0]['cells'] for m in models))

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
