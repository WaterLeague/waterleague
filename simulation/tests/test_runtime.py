import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from waterleague_sim.runtime import database_url


class RuntimeSecretTests(unittest.TestCase):
    def test_environment_and_file_are_mutually_exclusive(self):
        with patch.dict(os.environ, {'DATABASE_URL': 'test-url'}, clear=True):
            self.assertEqual('test-url', database_url())
            os.environ['DATABASE_URL_FILE'] = '/absent'
            with self.assertRaisesRegex(ValueError, '^DB_CONFIGURATION_AMBIGUOUS$'):
                database_url()

    def test_file_is_read_without_environment_export(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'secret'
            source.write_text('test-file-url\n')
            with patch.dict(os.environ, {'DATABASE_URL_FILE': str(source)}, clear=True):
                self.assertEqual('test-file-url', database_url())
                self.assertNotIn('DATABASE_URL', os.environ)

    def test_rejects_links_special_files_large_and_invalid_encoding_without_values(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'secret'
            source.write_text('private-value')
            (root / 'link').symlink_to(source)
            (root / 'large').write_bytes(b'x' * 8193)
            (root / 'invalid').write_bytes(b'private-value\xff')
            os.mkfifo(root / 'pipe')
            for path in (root, root / 'link', root / 'large', root / 'invalid', root / 'pipe', root / 'absent'):
                with self.subTest(path=path.name), patch.dict(os.environ, {'DATABASE_URL_FILE': str(path)}, clear=True):
                    with self.assertRaisesRegex(ValueError, '^DB_SECRET_FILE_INVALID$'):
                        database_url()

    def test_missing_or_empty_secret(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, '^DB_CONFIGURATION_MISSING$'):
                database_url()
        with tempfile.NamedTemporaryFile() as source, patch.dict(os.environ, {'DATABASE_URL_FILE': source.name}, clear=True):
            with self.assertRaisesRegex(ValueError, '^DB_CONFIGURATION_MISSING$'):
                database_url()
