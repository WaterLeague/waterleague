from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

from scripts.replay_coupled_bundle import load, safe_path, main, sha


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

    def test_unlisted_native_reference_rejected_before_loading_archived_code(self):
        for kind, names in [('coupled', ('coupled-input.json', 'coupled-result.json')),
                            ('inlet-network', ('original.inp', 'design.json', 'transformation.json',
                             'network/network-result.json', 'network/network.inp')),
                            ('refined-inlet-network', ('original.inp', 'design.json', 'transformation.json',
                             'network/network-result.json', 'network/network.inp', 'refinement.json',
                             'numerical-profile.json', 'prepared.inp', 'experiment-result.json'))]:
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                for name in (*names, 'network/network.out'):
                    path = root/'case'/name; path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text('{}')
                manifest = root/'manifest.json'
                manifest.write_text(json.dumps({'files': {f'case/{name}': sha(root/'case'/name) for name in names}}))
                args = ['replay', '--kind', kind, '--bundle', str(root), '--case', 'case',
                        '--manifest-sha256', sha(manifest), '--output', str(root/'result')]
                with patch('sys.argv', args), self.assertRaisesRegex(ValueError, 'REPLAY_CASE_MISSING'):
                    main()


if __name__ == '__main__': unittest.main()
