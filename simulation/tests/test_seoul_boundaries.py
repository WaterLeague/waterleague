import json
from pathlib import Path
import sys
import unittest

import shapely
from shapely.geometry import shape

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import prepare_seoul_boundaries as boundaries
import prepare_seoul_topography as source


class SeoulBoundariesTests(unittest.TestCase):
    def test_public_boundary_snapshot_has_25_unique_source_codes_and_full_original_geometry(self):
        data = json.loads(boundaries.OUTPUT.read_text())
        self.assertEqual(len(data['districts']), 25)
        self.assertEqual(len({d['id'] for d in data['districts']}), 25)
        source_names = {f['district'] for f in json.loads((source.ROOT / source.MANIFEST).read_text())['files']
                        if f['role'] == 'DISTRICT_TILE_PACKAGE'}
        self.assertEqual({d['name'] for d in data['districts']}, source_names)
        polygons = []
        for entry in data['districts']:
            geometry = shape(entry['nativeGeometry'])
            self.assertTrue(geometry.is_valid)
            self.assertEqual(geometry.area, entry['areaM2'])
            self.assertTrue(geometry.covers(shapely.Point(entry['centerProjected'])))
            self.assertEqual(entry['id'], entry['originalAttributes']['SIGNGU_CD'])
            self.assertIn(boundaries.ARCHIVE_SHA256, entry['sourceRecordId'])
            polygons.append(geometry)
        self.assertTrue(shapely.union_all(polygons).equals_exact(shape(data['boundary']), tolerance=0))

    def test_provenance_transform_and_scope_remain_explicit(self):
        data = json.loads(boundaries.OUTPUT.read_text())
        self.assertEqual(data['sourceSha256'], boundaries.ARCHIVE_SHA256)
        self.assertEqual(data['generatorSha256'], source.digest(Path(boundaries.__file__).read_bytes()))
        self.assertEqual(data['coordinateSystem'], 'EPSG:5186')
        self.assertIn('False_Northing",500000.0', data['originalWkt'])
        self.assertFalse(data['transform']['ballparkAllowed'])
        self.assertFalse(data['clipsHydrologicDomain'])
        self.assertFalse(data['geometryRepair'])
        self.assertIsNone(data['geometryReferenceDate'])
        self.assertEqual(data['license'], 'KOGL-TYPE1')


if __name__ == '__main__':
    unittest.main()
