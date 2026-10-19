from contextlib import closing
from decimal import Decimal
import json
from pathlib import Path
import sqlite3
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

import shapely

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import prepare_seoul_spatial as spatial
import prepare_seoul_topography as source
import topography_catalog as native
import verify_seoul_spatial as reference
import test_seoul_topography as fixtures
from test_seoul_topography import components, tile_bytes, TILE, LAYER


def shape_content(parts, kind=5):
    points = [point for part in parts for point in part]
    bounds = min(p[0] for p in points), min(p[1] for p in points), max(p[0] for p in points), max(p[1] for p in points)
    indexes, cursor = [], 0
    for part in parts:
        indexes.append(cursor)
        cursor += len(part)
    return (struct.pack('<I4d2I', kind, *bounds, len(parts), len(points))
            + struct.pack(f'<{len(parts)}I', *indexes)
            + b''.join(struct.pack('<2d', *point) for point in points))


def square(x=0, y=0, size=10):
    return [(x, y), (x, y + size), (x + size, y + size), (x + size, y), (x, y)]


class SeoulSpatialTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()

    def inputs(self, parts=None):
        path, _ = fixtures.SeoulTopographyTests.manifest(self, {'가구': [(TILE, tile_bytes(parts))]})
        summary = source.build(path, self.root / 'inputs', root=self.root)
        return native.SourceCatalog(self.root / 'inputs', summary), summary

    def test_source_catalog_rejects_database_and_tile_hash_changes(self):
        catalog, summary = self.inputs()
        rows = list(catalog.layers(TILE))
        layer, checksum, metadata, parts = rows[0]
        records = list(native.records(TILE, layer, checksum, metadata, parts))
        self.assertEqual(records[0]['attributes']['명칭'], '가동')
        self.assertIsNone(records[0]['attributes']['층수'])
        self.assertNotEqual(records[0]['id'], records[1]['id'])
        path = self.root / 'inputs/tiles' / (TILE + '.zip')
        path.write_bytes(path.read_bytes() + b'tampered')
        with self.assertRaises(source.TopographyDataError):
            list(catalog.layers(TILE))
        database = self.root / 'inputs/catalog.sqlite'
        with database.open('ab') as stream:
            stream.write(b'tampered')
        with self.assertRaises(source.TopographyDataError):
            native.SourceCatalog(self.root / 'inputs', summary)

    def test_polygon_holes_multipart_and_original_vertex_order_are_preserved(self):
        shell, second, hole = square(), square(20), list(reversed(square(2, 2, 4)))
        original = shape_content([hole, second, shell])
        result = native.native_geometry(original)
        self.assertEqual(result['status'], 'VALID')
        self.assertEqual(result['partMapping'], [[1], [2, 0]])
        self.assertEqual(result['geometry'].area, 184)
        self.assertEqual(list(result['geometry'].geoms[0].exterior.coords), second)
        self.assertEqual(list(result['geometry'].geoms[1].exterior.coords), shell)
        self.assertEqual(list(result['geometry'].geoms[1].interiors[0].coords), hole)
        self.assertEqual(shapely.get_num_coordinates(result['geometry']), 15)
        self.assertEqual(original, shape_content([hole, second, shell]))

    def test_invalid_rings_are_neither_closed_reoriented_nor_repaired(self):
        cases = [square()[:-1], list(reversed(square())), [(0, 0), (10, 10), (0, 10), (10, 0), (0, 0)]]
        for ring in cases:
            original = shape_content([ring])
            with self.subTest(ring=ring):
                result = native.native_geometry(original)
                self.assertEqual(result['status'], 'INVALID')
                self.assertEqual(original, shape_content([ring]))
        hole_outside = list(reversed(square(20)))
        result = native.native_geometry(shape_content([square(), hole_outside]))
        self.assertEqual(result['detail'], 'HOLE_WITHOUT_UNIQUE_SHELL')
        self.assertIsNone(result['geometry'])

    def test_raw_bbox_difference_uses_actual_coordinates_and_preserves_line_parts(self):
        original = bytearray(shape_content([[(0, 0), (10, 1)], [(20, 2), (30, 3)]], kind=3))
        struct.pack_into('<d', original, 4, -5)
        result = native.native_geometry(original)
        self.assertFalse(result['bboxMatches'])
        self.assertEqual(result['bounds'], (0, 0, 30, 3))
        self.assertEqual(result['status'], 'VALID')
        self.assertEqual(list(result['geometry'].geoms[1].coords), [(20, 2), (30, 3)])
        point = native.native_geometry(struct.pack('<I2d', 1, 200000.1, 550000.2))
        self.assertEqual(point['geometry'].x, 200000.1)
        self.assertEqual(native.native_geometry(struct.pack('<I', 0))['status'], 'NULL_SHAPE')

    def test_code_meaning_separates_unknown_unclassified_missing_and_scale(self):
        semantics = native.read_json(native.SEMANTICS_PATH)
        domain = semantics['domains']['buildingKind']
        self.assertEqual(native.code_meaning(None, domain)['status'], 'MISSING')
        self.assertEqual(native.code_meaning('미분류', domain)['status'], 'UNCLASSIFIED')
        self.assertEqual(native.code_meaning('BDK000', domain)['status'], 'UNCLASSIFIED')
        self.assertEqual(native.code_meaning('미등록값', domain)['status'], 'UNKNOWN_VALUE')
        self.assertEqual(native.code_meaning('아파트', domain)['code'], 'BDK003')
        pavement = semantics['domains']['roadPavement']
        self.assertEqual(native.code_meaning('RDQ006', pavement, 1000)['status'], 'OUTSIDE_LISTED_SCALE')
        self.assertEqual(native.code_meaning('RDQ006', pavement, 5000)['status'], 'KNOWN')
        for value in [None, 'NaN', 'Infinity', '****', '1e3', '0', '-1', '2.3500']:
            parsed, status = native.numeric_value(value)
            if value in ('0', '-1', '2.3500'):
                self.assertEqual(parsed, Decimal(value))
                self.assertEqual(status, 'VALUE')
            else:
                self.assertIsNone(parsed)

    def test_normalized_catalog_reproducibility_spatial_query_and_model_area_agree(self):
        catalog, _ = self.inputs()
        first = spatial.build(catalog, self.root / 'a')
        second = spatial.build(catalog, self.root / 'b')
        self.assertEqual(first, second)
        for name in ('spatial.sqlite', 'summary.json', 'code-values.json'):
            self.assertEqual((self.root / 'a' / name).read_bytes(), (self.root / 'b' / name).read_bytes())
        view = native.SpatialCatalog(self.root / 'a', first)
        records = view.query((199999, 549999, 200011, 550011), layers=[LAYER])
        self.assertEqual(len(records), 2)
        for record in records:
            self.assertEqual(record['geometry'].area, record['areaM2'])
            self.assertEqual(record['areaM2'], 64)
            self.assertEqual(record['spatialCatalogSha256'], first['spatialSha256'])
            self.assertEqual(record['attributes']['UFID'], 'same')
            self.assertIsNone(record['attributes']['층수'])
        self.assertNotEqual(records[0]['id'], records[1]['id'])
        self.assertEqual(view.query((200003, 550003, 200007, 550007), layers=[LAYER]), [])
        with self.assertRaises(source.TopographyDataError):
            view.query((199999, 549999, 200011, 550011), limit=1)
        with self.assertRaises(source.TopographyDataError):
            spatial.build(catalog, self.root / 'a')

    def test_deleted_records_remain_auditable_but_have_no_eligible_area(self):
        catalog, _ = self.inputs(components(deleted=(False, True)))
        report = spatial.build(catalog, self.root / 'spatial')
        self.assertEqual(report['counts']['records'], 2)
        self.assertEqual(report['counts']['deleted'], 1)
        records = native.SpatialCatalog(self.root / 'spatial', report).query((199999, 549999, 200011, 550011))
        self.assertEqual(len(records), 1)
        with closing(sqlite3.connect(self.root / 'spatial/spatial.sqlite')) as connection:
            self.assertIsNone(connection.execute('SELECT area_m2 FROM features WHERE deleted=1').fetchone()[0])

    def test_manual_layer_differences_and_unlisted_codes_remain_explicit(self):
        semantics = native.read_json(native.SEMANTICS_PATH)
        self.assertEqual(semantics['layers']['N1A_A0033320']['manualMatch'], 'GEOMETRY_DIFFERS')
        self.assertEqual(semantics['layers']['N3A_A0043325']['manualMatch'], 'SCALE_NOT_LISTED')
        self.assertEqual(semantics['layers']['N1L_A0033330']['role'], 'UNKNOWN')
        self.assertEqual(semantics['layers']['N3A_B0010000']['scaleDenominator'], 5000)
        metadata = source.inspect_layer(LAYER, components())
        comparison = spatial.schema_comparison(metadata, LAYER, semantics)
        self.assertIn('SCLS', comparison['missingManualFields'])
        self.assertIn('FMTA', comparison['missingManualFields'])
        self.assertEqual(comparison['manualMatchedFields']['NMLY'], '층수')

    def test_partial_build_cleanup_and_query_validation(self):
        catalog, _ = self.inputs()
        with patch.object(native, 'native_geometry', side_effect=source.TopographyDataError('검사 실패')):
            with self.assertRaises(source.TopographyDataError):
                spatial.build(catalog, self.root / 'failed')
        self.assertFalse((self.root / 'failed').exists())
        report = spatial.build(catalog, self.root / 'spatial')
        view = native.SpatialCatalog(self.root / 'spatial', report)
        for bounds in [(0, 0, 0, 1), (0, 0, float('nan'), 1), (1, 0, 0, 1)]:
            with self.assertRaises(source.TopographyDataError):
                view.query(bounds)
        with self.assertRaises(source.TopographyDataError):
            view.query((0, 0, 1, 1), layers=['N1A_B0010000;DROP'])
        path = self.root / 'spatial/spatial.sqlite'
        with path.open('ab') as stream:
            stream.write(b'tampered')
        with self.assertRaises(source.TopographyDataError):
            native.SpatialCatalog(self.root / 'spatial', report)

    def test_independent_reference_verifier_rejects_shape_and_record_changes(self):
        catalog, _ = self.inputs()
        layer, checksum, metadata, parts = next(catalog.layers(TILE))
        records = list(native.records(TILE, layer, checksum, metadata, parts))
        features = [{'id': record['number'] - 1, 'geometry': json.loads(shapely.to_geojson(
                     native.native_geometry(record['rawShape'])['geometry']))} for record in records]
        self.assertEqual(reference.compare(records, features)['comparedValidGeometry'], 2)
        features[0]['id'] = 99
        with self.assertRaises(source.TopographyDataError):
            reference.compare(records, features)
        features[0]['id'] = 0
        features[0]['geometry']['coordinates'][0][0][0] += .01
        with self.assertRaises(source.TopographyDataError):
            reference.compare(records, features)

    def test_changed_inputs_during_normalization_cannot_publish_a_catalog(self):
        catalog, _ = self.inputs()
        original = native.native_geometry
        mutated = False

        def mutate(content):
            nonlocal mutated
            if not mutated:
                with catalog.database.open('ab') as stream:
                    stream.write(b'changed during normalization')
                mutated = True
            return original(content)

        with patch.object(native, 'native_geometry', side_effect=mutate):
            with self.assertRaises(source.TopographyDataError):
                spatial.build(catalog, self.root / 'failed')
        self.assertFalse((self.root / 'failed').exists())

    def test_published_native_catalog_is_bound_to_current_code_and_source(self):
        report = native.read_json(source.ROOT / 'data/manifests/seoul-spatial-catalog-v1.json')
        inputs = native.read_json(spatial.SOURCE_SUMMARY)
        for key, path in [('generatorSha256', spatial.__file__), ('readerSha256', native.__file__),
                          ('sourceReaderSha256', source.__file__), ('semanticsSha256', native.SEMANTICS_PATH)]:
            self.assertEqual(report[key], spatial.file_sha256(path))
        self.assertEqual(report['sourceCatalogSha256'], inputs['catalogSha256'])
        self.assertEqual(report['counts']['records'], inputs['counts']['rawRecords'])
        self.assertEqual(sum(v['records'] for v in report['layerCounts'].values()), report['counts']['records'])
        self.assertEqual(report['independentGdalComparison']['readerSha256'], report['readerSha256'])
        self.assertEqual(report['independentGdalComparison']['verifierSha256'], spatial.file_sha256(reference.__file__))
        for key in ('seoulCoverageVerified', 'tileSeamsVerified', 'serviceMigrated', 'geometryRepair'):
            self.assertFalse(report['policy'][key])


if __name__ == '__main__':
    unittest.main()
