import hashlib
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import prepare_topography_objects as objects
import prepare_topography_scene as scene
import audit_topography_seams as seams
import prepare_seoul_topography as source
import verify_topography_scene as verification


class TopographyPublicContractTests(unittest.TestCase):
    def read(self, filename):
        return json.loads((source.ROOT / 'data/manifests' / filename).read_text())

    def assert_binding(self, value, producer):
        self.assertEqual(value['generatorSha256'], source.digest(Path(producer.__file__).read_bytes()))
        expected = self.read('seoul-spatial-catalog-v1.json')
        self.assertEqual(value['sourceSpatialSha256'], expected['spatialSha256'])
        boundary = source.ROOT / value['districtBoundary']['file']
        self.assertEqual(hashlib.sha256(boundary.read_bytes()).hexdigest(), value['districtBoundary']['sha256'])
        self.assertEqual(source.digest(source.canonical(json.loads(boundary.read_text())).encode()), value['boundaryContentSha256'])
        self.assertFalse(value['serviceMigrated'])

    def test_object_catalog_preserves_source_balance_and_conservative_placement_policy(self):
        value = self.read('seoul-topography-objects-v1.json')
        self.assert_binding(value, objects)
        counts = value['counts']
        self.assertEqual(counts['sourceRecords'], counts['objects'] + counts['outsideCityRecords'] + counts.get('coincidentSourceRecords', 0))
        self.assertEqual(sum(v['objects'] for v in value['roleCounts'].values()), counts['objects'])
        self.assertFalse(value['policy']['ufidOnlyMerging'])
        self.assertFalse(value['policy']['clipsGeometryToDistrict'])
        self.assertFalse(value['policy']['overlappingBuildingsArePlacementEligible'])
        self.assertGreater(counts['buildingObjectsWithOverlap'], 0)

    def test_coverage_is_balanced_per_district_and_does_not_claim_full_city_support(self):
        value = self.read('seoul-topography-coverage-v1.json')
        self.assert_binding(value, seams)
        coverage = value['coverage']
        self.assertEqual(len(coverage['districts']), 25)
        self.assertEqual(coverage['missingFrameTiles'], [])
        self.assertGreater(coverage['uncoveredM2'], 0)
        self.assertAlmostEqual(coverage['cityAreaM2'], coverage['covered1000M2'] + coverage['additional5000M2'] + coverage['uncoveredM2'], places=5)
        for district in coverage['districts'].values():
            self.assertAlmostEqual(district['districtAreaM2'], district['covered1000M2'] + district['additional5000M2'] + district['uncoveredM2'], places=5)
        self.assertFalse(value['policy']['joinsApplied'])
        self.assertFalse(value['policy']['fieldAccuracyVerified'])

    def test_scene_and_full_comparison_bind_the_same_object_snapshot(self):
        value = self.read('seoul-topography-scene-v1.json')
        self.assert_binding(value, scene)
        expected = self.read('seoul-topography-objects-v1.json')
        self.assertEqual(value['objectsSha256'], expected['objectsSha256'])
        self.assertEqual(value['validation']['objectsCompared'], expected['counts']['objects'])
        self.assertEqual(value['validation']['catalogSha256'], value['catalog']['sha256'])
        self.assertEqual(value['validation']['verifierSha256'], source.digest(Path(verification.__file__).read_bytes()))
        self.assertFalse(value['validation']['browserPerformanceVerified'])


if __name__ == '__main__':
    unittest.main()
