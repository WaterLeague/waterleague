"""공개 서울 전역 타일의 등록 무결성·분할 누락 검사."""
import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class SeoulCityTests(unittest.TestCase):
    def test_all_registered_tiles_hashes_ids_and_counts(self):
        folder = ROOT/'frontend/public/data/seoul-v1'
        raw = (folder/'city.json').read_bytes()
        manifest = json.loads((ROOT/'data/manifests/seoul-city-v1.json').read_text())
        city = json.loads(raw)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), manifest['city']['sha256'])
        self.assertEqual(hashlib.sha256((ROOT/'scripts/prepare_seoul_city.py').read_bytes()).hexdigest(), manifest['generatorSha256'])
        self.assertEqual(len(city['districts']), 25)
        identifiers = set()
        for entry in city['tiles']:
            payload = (folder/entry['file']).read_bytes()
            self.assertEqual(len(payload), entry['bytes'])
            self.assertEqual(hashlib.sha256(payload).hexdigest(), entry['sha256'])
            tile = json.loads(payload)
            self.assertEqual(tile['id'], entry['id'])
            self.assertEqual(len(tile['buildings']), entry['buildingCount'])
            for building in tile['buildings']:
                self.assertNotIn(building['id'], identifiers)
                identifiers.add(building['id'])
        self.assertEqual(len(identifiers), city['buildingCount'])
        self.assertEqual(len(identifiers), manifest['buildingCount'])
        self.assertFalse(manifest['modelInput'])
        self.assertEqual(city['sourceSha256'],manifest['sourceSha256'])
