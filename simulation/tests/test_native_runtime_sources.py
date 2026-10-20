"""현재 서비스가 보관 공간 모델 없이 읽는 공개 입력·원문·경로 검사."""
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from waterleague_sim.current_model_catalog import read_current_catalog
from waterleague_sim.engine.swmm import ROOT
from waterleague_sim.forcing import archived_game_weather as weather
from waterleague_sim.spatial import game_catalog


class NativeRuntimeSourceTests(unittest.TestCase):
    def test_current_research_models_keep_exact_native_bytes_without_archived_models(self):
        expected = read_current_catalog(ROOT / 'data/models')
        self.assertEqual(len(expected), 4)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            shutil.copytree(ROOT / 'data/models/current', root / 'current')
            self.assertEqual(expected, read_current_catalog(root))
            for checksum, source in expected.items():
                self.assertEqual(checksum, hashlib.sha256(source).hexdigest())
                self.assertEqual(json.loads(source)['mapId'], 'seongsu-ngii-2025-v2')
            path = root / 'current/catalog.json'
            path.write_bytes(path.read_bytes() + b' ')
            with self.assertRaisesRegex(ValueError, 'CURRENT_MODEL_CATALOG_INVALID'):
                read_current_catalog(root)

    def test_packaged_observations_keep_every_registered_original_and_no_private_inputs(self):
        raw = (weather.DIRECTORY / 'manifest.json').read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), weather.MANIFEST_SHA256)
        manifest = json.loads(raw)
        files = {row['file']: row for row in manifest['files']}
        self.assertEqual(manifest['forcingCatalogSha256'], game_catalog.SHA256)
        self.assertEqual(len(files), 1800)
        for relative, expected in game_catalog.catalog()['sourceHashes'].items():
            self.assertEqual(files[relative]['sha256'], expected)
        for relative, row in files.items():
            self.assertNotIn('private', Path(relative).parts)
            self.assertNotIn('tests', Path(relative).parts)
            self.assertEqual(len(weather.read_source(relative, row['sha256'])), row['bytes'])
        for checksum, relative in manifest['implementationFiles'].items():
            self.assertEqual(weather.implementation_source(checksum), weather.read_source(relative, checksum))
        with self.assertRaisesRegex(ValueError, 'OBSERVED_SOURCE_REFERENCE_INVALID'):
            weather.read_source('../secret.json', '0' * 64)
        relative = next(iter(files))
        with self.assertRaisesRegex(ValueError, 'OBSERVED_SOURCE_REFERENCE_INVALID'):
            weather.read_source(relative, '0' * 64)

    def test_linked_weather_directory_is_rejected_before_archive_access(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            linked = root / 'linked'
            linked.symlink_to(weather.DIRECTORY, target_is_directory=True)
            weather._sources.cache_clear()
            try:
                with patch.object(weather, 'DIRECTORY', linked):
                    with self.assertRaisesRegex(ValueError, 'OBSERVED_SOURCE_ARCHIVE_INVALID'):
                        weather._sources()
            finally:
                weather._sources.cache_clear()


if __name__ == '__main__':
    unittest.main()
