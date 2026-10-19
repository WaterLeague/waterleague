"""CI 공개 원문 복원과 기존 자료·링크 보호 확인."""
from pathlib import Path
import gzip
import json
import tempfile
import unittest

from scripts.prepare_ci_sources import FIXTURES, ROOT, prepare


class CiSourceTests(unittest.TestCase):
    def test_restore_is_repeatable_and_preserves_changed_existing_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            count = len(json.loads((FIXTURES / 'public-sources-v1.json').read_text())['files'])
            self.assertEqual(count, prepare(root))
            self.assertEqual(count, prepare(root))
            path = root / 'data/raw/kma-421-202208081800-202208082359.txt'
            path.write_bytes(b'changed-local-source')
            with self.assertRaisesRegex(ValueError, 'EXISTING_SOURCE_CHANGED'):
                prepare(root)
            self.assertEqual(b'changed-local-source', path.read_bytes())

    def test_all_archived_weather_originals_are_packaged(self):
        packaged = {row['path']: row['sha256']
                    for row in json.loads((FIXTURES / 'public-sources-v1.json').read_text())['files']}
        archives = [json.loads(path.read_bytes()) for path in
                    (ROOT / 'data/derived/evaporation').glob('seoul-*-fao56-v1.json')]
        for path in (ROOT / 'data/derived/surface-antecedent').glob('*.gz'):
            value = json.loads(gzip.decompress(path.read_bytes()))
            archives.extend((value['rainfall'], value['evaporation']))
        archives.extend(json.loads(gzip.decompress(path.read_bytes()))
                        for path in (ROOT / 'data/derived/antecedent').glob('*.gz'))
        self.assertTrue(archives)
        for value in archives:
            for source in value['sourceRequests']:
                self.assertEqual(source['sha256'], packaged.get(source['rawFile']), source['rawFile'])

    def test_linked_parent_is_rejected_before_writes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            outside = root / 'outside'
            outside.mkdir()
            (root / 'data').symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, 'SOURCE_PATH_INVALID'):
                prepare(root)
            self.assertEqual([], list(outside.iterdir()))
