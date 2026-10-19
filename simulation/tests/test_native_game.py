"""공개 행정구·원형 후보·보관 기상 결속의 독립 재생성 검사."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import prepare_native_game as generation
import verify_native_game as verification
from waterleague_sim.spatial import game_catalog
from waterleague_sim.spatial.play_catalog import NativeCatalogError


class NativeGameTests(unittest.TestCase):
    def test_all_bindings_keep_the_exact_observed_rainfall_without_legacy_geometry(self):
        registry = game_catalog.catalog()
        self.assertEqual(registry['generatorSha256'], generation.spatial.file_sha256(generation.__file__))
        for relative, expected in registry['sourceHashes'].items():
            self.assertEqual(expected, generation.spatial.file_sha256(generation.source.ROOT / relative), relative)
        packaged = {row['path']: row['sha256'] for row in json.loads((generation.source.ROOT /
            'simulation/tests/fixtures/public-sources-v1.json').read_bytes())['files']}
        districts, bindings = set(), {}
        for region in registry['regions']:
            self.assertRegex(region['districtId'], r'^11\d{3}$')
            self.assertNotIn(region['districtId'], districts)
            districts.add(region['districtId'])
            self.assertEqual(len(region['modelHashes']), 4)
            for checksum in region['modelHashes']:
                body = json.loads(game_catalog.forcing(checksum))
                original = json.loads((generation.source.ROOT / body['sourceRainfallFile']).read_bytes())
                self.assertEqual(body['districtId'], region['districtId'])
                self.assertEqual(body['siteCatalogSha256'], generation.PLAY_SHA256)
                self.assertEqual(body['mapId'], 'seoul-ngii-v1-' + region['districtId'])
                self.assertNotIn('cells', body)
                self.assertEqual({k: v for k, v in original.items() if k not in ('stationDistanceKm', 'stationDistanceEvidence')},
                    {k: v for k, v in body['rainfall'].items() if k not in ('stationDistanceKm', 'stationDistanceEvidence')})
                self.assertLessEqual(body['rainfall']['stationDistanceKm'], 10)
                self.assertEqual(len(body['stationPoolIds']), len(set(body['stationPoolIds'])))
                bindings[checksum] = body
        self.assertEqual(len(districts), 25)
        self.assertEqual(len(bindings), 100)
        pet, _ = game_catalog.climate_binding('evaporation', next(sha for sha, b in bindings.items() if 'disasterEvent' in b))
        antecedent, _ = game_catalog.climate_binding('antecedent', next(sha for sha, b in bindings.items() if 'disasterEvent' in b))
        hashes = {}
        generation.verify_climate(bindings, pet, antecedent, hashes)
        for relative, checksum in hashes.items():
            self.assertEqual(checksum, registry['sourceHashes'][relative])
            if relative.startswith('data/raw/'):
                self.assertEqual(checksum, packaged.get(relative), relative)

    def test_rebuild_is_deterministic_and_matches_the_published_inputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            first = generation.build(root / 'first')
            second = generation.build(root / 'second')
            self.assertEqual(first, second)
            published = game_catalog.catalog()
            # PROJ 배포 차이는 버전 필드로 남기며 좌표·관측·선정 결과는 같아야 한다.
            first.pop('versions')
            published.pop('versions')
            self.assertEqual(first, published)
            paths = [path.relative_to(root / 'first') for path in (root / 'first').rglob('*.json')]
            self.assertEqual(len(paths), 104)
            for relative in paths:
                self.assertEqual((root / 'first' / relative).read_bytes(), (root / 'second' / relative).read_bytes())

    def test_wrong_rain_source_or_partial_climate_binding_is_rejected(self):
        entry = game_catalog.catalog()['models'][0]
        body = json.loads(game_catalog.forcing(entry['sha256']))
        altered = copy.deepcopy(body['rainfall'])
        altered['depthsMm'][0] += 1
        with self.assertRaisesRegex(ValueError, '강우 불일치'):
            generation.verify_rain(altered, {})
        altered = copy.deepcopy(body['rainfall'])
        altered['sourceManifest'] = '../private.json'
        with self.assertRaisesRegex(ValueError, '출처 오류'):
            generation.verify_rain(altered, {})
        checksum = next(row['sha256'] for row in game_catalog.catalog()['models'] if row['eventId'] != 'default')
        event = json.loads(game_catalog.forcing(checksum))
        pet, _ = game_catalog.climate_binding('evaporation', checksum)
        with self.assertRaisesRegex(ValueError, '결속 누락'):
            generation.verify_climate({checksum: event}, pet, {'entries': []}, {})

    def test_unavailable_observation_is_not_replaced_and_cached_snapshots_are_independent(self):
        with self.assertRaisesRegex(ValueError, '10km'):
            generation.nearest([200000, 550000], {})
        with self.assertRaises(NativeCatalogError):
            game_catalog.forcing('0' * 64)
        checksum = game_catalog.catalog()['regions'][0]['defaultModelHash']
        with self.assertRaises(NativeCatalogError):
            game_catalog.climate_binding('antecedent', checksum)
        with self.assertRaises(NativeCatalogError):
            game_catalog.climate_binding('../private', checksum)
        view = game_catalog.catalog()
        view['regions'].clear()
        self.assertEqual(len(game_catalog.regions()), 25)

    def test_existing_output_and_linked_parent_are_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            sentinel = root / 'existing'
            sentinel.mkdir()
            (sentinel / 'keep.txt').write_text('keep')
            with self.assertRaises(ValueError):
                generation.build(sentinel)
            self.assertEqual((sentinel / 'keep.txt').read_text(), 'keep')
            (root / 'linked').symlink_to(sentinel, target_is_directory=True)
            with self.assertRaises(ValueError):
                generation.build(root / 'linked' / 'new')
            self.assertFalse((sentinel / 'new').exists())

    def test_runtime_reader_rejects_links_and_oversized_resources(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            path = root / 'source.json'
            path.write_bytes(b'x' * 32)
            with patch.object(game_catalog, 'DIRECTORY', root):
                with self.assertRaises(NativeCatalogError):
                    game_catalog._read('source.json', 16)
                (root / 'linked.json').symlink_to(path)
                with self.assertRaises(NativeCatalogError):
                    game_catalog._read('linked.json')
                self.assertEqual(game_catalog._read('source.json'), b'x' * 32)

    def test_published_runtime_evidence_binds_current_readers_and_all_regions(self):
        root = generation.source.ROOT
        report = json.loads((root / 'data/benchmarks/native-game-runtime-v1.json').read_bytes())
        self.assertEqual(report['catalogSha256'], game_catalog.SHA256)
        self.assertEqual(report['districtCount'], 25)
        self.assertEqual(report['observationBindingsCompared'], 100)
        self.assertEqual(report['disasterBindingsWithSevenDayInputs'], 75)
        self.assertTrue(report['apiWorkerForcingJsonMatched'])
        self.assertTrue(report['rainfallRecomputedFromOriginal'])
        self.assertFalse(report['observedRainfallChanged'])
        self.assertFalse(report['fieldRepresentativenessVerified'])
        self.assertFalse(report['gameRuntimeMigrated'])
        for relative, checksum in report['implementationHashes'].items():
            self.assertEqual(checksum, generation.spatial.file_sha256(root / relative), relative)
        self.assertIn(str(Path(verification.__file__).resolve().relative_to(root)), report['implementationHashes'])


if __name__ == '__main__':
    unittest.main()
