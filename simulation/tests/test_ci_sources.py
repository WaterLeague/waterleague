"""CI 공개 원문 복원과 기존 자료·링크 보호 확인."""
from pathlib import Path
import tempfile
import unittest

from scripts.prepare_ci_sources import prepare


class CiSourceTests(unittest.TestCase):
    def test_restore_is_repeatable_and_preserves_changed_existing_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            self.assertEqual(17, prepare(root))
            self.assertEqual(17, prepare(root))
            path = root / 'data/raw/kma-421-202208081800-202208082359.txt'
            path.write_bytes(b'changed-local-source')
            with self.assertRaisesRegex(ValueError, 'EXISTING_SOURCE_CHANGED'):
                prepare(root)
            self.assertEqual(b'changed-local-source', path.read_bytes())

    def test_linked_parent_is_rejected_before_writes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            outside = root / 'outside'
            outside.mkdir()
            (root / 'data').symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, 'SOURCE_PATH_INVALID'):
                prepare(root)
            self.assertEqual([], list(outside.iterdir()))
