from contextlib import closing
import json
from pathlib import Path
import sqlite3
import struct
import sys
import tempfile
import unittest

import shapely
from shapely.geometry import box, mapping

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import prepare_topography_objects as objects
import prepare_seoul_spatial as spatial
import prepare_seoul_topography as source
import topography_catalog as native
import test_seoul_topography as fixtures


def boundaries():
    return {'districts': [
        {'id': '11110', 'name': '시험구1', 'nativeGeometry': mapping(box(199999, 549999, 200005, 550011))},
        {'id': '11140', 'name': '시험구2', 'nativeGeometry': mapping(box(200005, 549999, 200013, 550011))}]}


class TopographyObjectsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()

    def catalog(self, parts=None):
        path, _ = fixtures.SeoulTopographyTests.manifest(self, {'가구': [(fixtures.TILE, fixtures.tile_bytes(parts))]})
        summary = source.build(path, self.root / 'inputs', root=self.root)
        inputs = native.SourceCatalog(self.root / 'inputs', summary)
        output = self.root / 'spatial'
        report = spatial.build(inputs, output)
        return native.SpatialCatalog(output, report)

    def test_assignment_preserves_whole_geometry_and_explicit_cross_district_measures(self):
        assignment = objects.DistrictAssignment(boundaries())
        original = box(200000, 550000, 200010, 550010)
        code, parts = assignment.assign(original)
        self.assertEqual(code, '11110')
        self.assertEqual([p['intersectionMeasure'] for p in parts], [50, 50])
        self.assertEqual(original.area, 100)
        self.assertEqual(assignment.assign(box(0, 0, 1, 1)), (None, []))

    def test_only_exact_coincidence_is_grouped_without_snapping_or_ufid(self):
        a = box(0, 0, 10, 10)
        b = shapely.reverse(a)
        self.assertEqual(objects.object_key(fixtures.LAYER, a), objects.object_key(fixtures.LAYER, b))
        self.assertNotEqual(objects.object_key(fixtures.LAYER, a), objects.object_key(fixtures.LAYER, box(0, 0, 10.000000001, 10)))
        self.assertNotEqual(objects.object_key(fixtures.LAYER, a), objects.object_key('N1A_A0010000', a))

    def test_group_preserves_both_source_records_and_conflicting_attributes(self):
        catalog = self.catalog()
        report = objects.build(catalog, boundaries(), self.root / 'objects')
        self.assertEqual(report['counts']['objects'], 1)
        self.assertEqual(report['counts']['coincidentSourceRecords'], 1)
        self.assertEqual(report['counts']['attributeConflicts'], 1)
        self.assertFalse(report['policy']['coincidentIsAssetIdentity'])
        with closing(sqlite3.connect(self.root / 'objects/objects.sqlite')) as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM source_links').fetchone()[0], 2)
            self.assertEqual(connection.execute('SELECT source_count,area_m2,attribute_status FROM objects').fetchone(), (2, 64, 'CONFLICT'))
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM attribute_variants').fetchone()[0], 2)

    def test_different_ufids_do_not_duplicate_exact_geometry_area(self):
        parts = fixtures.components(names=('같은명칭', '같은명칭'), identifiers=('first', 'second'))
        catalog = self.catalog(parts)
        report = objects.build(catalog, boundaries(), self.root / 'objects')
        self.assertEqual(report['counts']['objects'], 1)
        self.assertEqual(report['counts']['attributeConflicts'], 0)
        with closing(sqlite3.connect(self.root / 'objects/objects.sqlite')) as connection:
            self.assertEqual(connection.execute('SELECT SUM(area_m2) FROM objects').fetchone()[0], 64)

    def test_positive_overlap_of_different_geometry_is_flagged(self):
        parts = fixtures.components()
        data = bytearray(parts['shp'])
        second, size = struct.unpack_from('>II', parts['shx'], 108)
        content_start = second * 2 + 8
        count = struct.unpack_from('<I', data, content_start + 36)[0]
        points = content_start + 44 + count * 4
        for pos in range(points, content_start + size * 2, 16):
            x = struct.unpack_from('<d', data, pos)[0]
            struct.pack_into('<d', data, pos, x + 2)
        for relative in (4, 20):
            old = struct.unpack_from('<d', data, content_start + relative)[0]
            struct.pack_into('<d', data, content_start + relative, old + 2)
        parts['shp'] = bytes(data)
        catalog = self.catalog(parts)
        report = objects.build(catalog, boundaries(), self.root / 'objects')
        self.assertEqual(report['counts']['objects'], 2)
        self.assertEqual(report['counts']['buildingOverlapPairs'], 1)
        self.assertEqual(report['counts']['buildingObjectsWithOverlap'], 2)
        self.assertFalse(report['policy']['overlappingBuildingsArePlacementEligible'])

    def test_reproducibility_and_no_overwrite(self):
        catalog = self.catalog()
        first = objects.build(catalog, boundaries(), self.root / 'a')
        second = objects.build(catalog, boundaries(), self.root / 'b')
        self.assertEqual(first, second)
        for name in ('objects.sqlite', 'summary.json'):
            self.assertEqual((self.root / 'a' / name).read_bytes(), (self.root / 'b' / name).read_bytes())
        with self.assertRaises(source.TopographyDataError):
            objects.build(catalog, boundaries(), self.root / 'a')


if __name__ == '__main__':
    unittest.main()
