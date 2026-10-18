from pathlib import Path
import tempfile
import unittest

from scripts.replay_coupled_bundle import load, safe_path


class ReplayBundleValidationTests(unittest.TestCase):
    def test_traversal_absolute_path_and_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            for value in ('../escape', '/absolute', ''):
                with self.assertRaisesRegex(ValueError, 'REPLAY_PATH_INVALID'): safe_path(root, value)
            (root/'alias').symlink_to(root)
            with self.assertRaisesRegex(ValueError, 'REPLAY_PATH_INVALID'): safe_path(root, 'alias/source.py')
            self.assertEqual(safe_path(root, 'source/a.py'), root/'source/a.py')

    def test_duplicate_and_nonfinite_json_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'manifest.json'
            for text, code in (('{"files":{},"files":{}}', 'DUPLICATE_KEY'),
                               ('{"value":NaN}', 'NONFINITE_VALUE')):
                path.write_text(text)
                with self.assertRaisesRegex(ValueError, code): load(path)


if __name__ == '__main__': unittest.main()
