from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

import shapely
from shapely.affinity import translate
from shapely.geometry import LineString, Polygon, box, mapping, shape

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import prepare_seoul_topography as source
import prepare_topography_objects as objects
import prepare_topography_scene as scene
import verify_topography_scene as verification


class TopographySceneTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()

    def test_full_polygon_holes_coordinates_and_source_measures_survive_display_translation(self):
        geometry = Polygon([(198000, 552000), (200001.123456789, 552000),
                            (200001.123456789, 552010), (198000, 552010)],
                           [[(198200, 552002), (198202, 552002), (198202, 552004), (198200, 552004)]])
        body, bounds = scene.display_record('source', 'BUILDING_FOOTPRINT', shapely.to_wkb(geometry),
            geometry.area, None, '11110', 'CONSISTENT', 0, {'층수': '4', '종류': '일반주택'})
        self.assertTrue(shape(body['geometry']).equals_exact(translate(geometry, -scene.ORIGIN[0], -scene.ORIGIN[1]), 0))
        self.assertEqual(bounds, geometry.bounds)
        self.assertEqual(body['sourceAreaM2'], geometry.area)
        self.assertIsNone(body['sourceLengthM'])
        self.assertEqual(body['heightM'], 12.8)
        self.assertEqual(body['heightBasis'], 'FLOOR_COUNT_DISPLAY_ASSUMPTION')
        self.assertEqual(body['constructionEligibility'], 'UNKNOWN')

    def test_missing_invalid_or_conflicting_floors_never_become_surveyed_height(self):
        raw = shapely.to_wkb(box(198100, 552000, 198110, 552010))
        for floors, status in [(None, 'CONSISTENT'), ('0', 'CONSISTENT'), ('3.5', 'CONSISTENT'),
                               ('201', 'CONSISTENT'), ('4', 'CONFLICT')]:
            with self.subTest(floors=floors, status=status):
                body, _ = scene.display_record('source', 'BUILDING_FOOTPRINT', raw, 100, 40,
                                               '11110', status, 0, {'층수': floors})
                self.assertIsNone(body['aboveGroundFloors'])
                self.assertEqual(body['heightM'], .3)
                self.assertEqual(body['heightBasis'], 'UNKNOWN_HEIGHT_FLAT_DISPLAY')
        body, _ = scene.display_record('source', 'BUILDING_FOOTPRINT', raw, 100, 40,
                                       '11110', 'CONSISTENT', 1, {'층수': '4'})
        self.assertEqual(body['geometryEligibility'], 'UNRESOLVED_OVERLAP')

    def test_unknown_road_direction_and_width_unit_are_not_inferred(self):
        raw = shapely.to_wkb(LineString([(198100, 552000), (198110, 552010)]))
        for value, expected in [(None, 'UNKNOWN'), ('일방통행', 'UNKNOWN'), ('양방통행', 'BIDIRECTIONAL')]:
            with self.subTest(value=value):
                body, _ = scene.display_record('road', 'ROAD_CENTERLINE', raw, 0, 14.14,
                    '11110', 'CONSISTENT', 0, {'일방통행': value, '도로폭': '8.0'})
                self.assertEqual(body['trafficDirection'], expected)
                self.assertEqual(body['reportedWidthRaw'], '8.0')
                self.assertEqual(body['reportedWidthUnit'], 'NOT_CONFIRMED')

    def inputs(self):
        directory = self.root / 'objects'
        directory.mkdir()
        geometry = box(198000, 552000, 200010, 552010)
        district = box(197000, 551000, 201000, 553000)
        boundaries = {'districts': [{'id': '11110', 'name': '시험구', 'areaM2': district.area,
            'centerProjected': list(district.representative_point().coords[0]), 'nativeGeometry': mapping(district)}]}
        identifier = objects.object_key('N1A_B0010000', geometry)
        with closing(sqlite3.connect(directory / 'objects.sqlite')) as database:
            objects.prepare_database(database)
            database.execute('''INSERT INTO objects(object_id,layer,role,representative_fid,geometry_wkb,
                area_m2,length_m,district_id,district_intersections) VALUES(?,?,?,?,?,?,?,?,?)''',
                (identifier, 'N1A_B0010000', 'BUILDING_FOOTPRINT', 1, shapely.to_wkb(geometry),
                 geometry.area, None, '11110', '[]'))
            properties = source.canonical({'층수': '2'})
            database.execute('INSERT INTO attribute_variants VALUES(?,?,?)',
                             (identifier, source.digest(properties.encode()), properties))
            database.commit()
        report = {'objectsSha256': source.digest((directory / 'objects.sqlite').read_bytes()),
            'sourceSpatialSha256': 'a' * 64,
            'decoderSha256': source.digest(Path(scene.native.__file__).read_bytes()),
            'counts': {'objects': 1},
            'boundaryContentSha256': source.digest(source.canonical(boundaries).encode())}
        (directory / 'summary.json').write_text(source.canonical(report))
        return directory, boundaries, identifier, geometry

    def test_repeated_builds_have_identical_hashes_and_tiles_use_full_object_bounds(self):
        directory, boundaries, identifier, geometry = self.inputs()
        first = scene.build(directory, boundaries, self.root / 'a')
        second = scene.build(directory, boundaries, self.root / 'b')
        self.assertEqual(first, second)
        catalog = json.loads((self.root / 'a/catalog.json').read_text())
        self.assertEqual(catalog['sourceObjectsSha256'], source.digest((directory / 'objects.sqlite').read_bytes()))
        self.assertFalse(catalog['policy']['geometryClippedToTile'])
        self.assertFalse(catalog['policy']['modelCalculationsFromDisplayGeometry'])
        self.assertFalse(catalog['policy']['serviceMigrated'])
        tile = catalog['tiles'][0]
        self.assertGreater(tile['bounds'][2] - tile['bounds'][0], scene.TILE_SIZE)
        payload = self.root / 'a' / tile['file']
        self.assertEqual(source.digest(payload.read_bytes()), tile['sha256'])
        feature = json.loads(payload.read_text())['features'][0]
        self.assertEqual(feature['id'], identifier)
        self.assertEqual(shape(feature['geometry']).area, geometry.area)
        self.assertEqual(payload.read_bytes(), (self.root / 'b' / tile['file']).read_bytes())
        self.assertFalse((self.root / 'a/staging.sqlite').exists())
        verified = verification.verify(self.root / 'a', directory)
        self.assertEqual(verified['objectsCompared'], 1)
        self.assertEqual(verified['status'], 'PASS')
        with self.assertRaises(source.TopographyDataError):
            scene.build(directory, boundaries, self.root / 'a')

    def test_whole_scene_comparison_rejects_clipped_geometry_and_repeated_object(self):
        directory, boundaries, _, _ = self.inputs()
        scene.build(directory, boundaries, self.root / 'a')
        catalog_path = self.root / 'a/catalog.json'
        catalog = json.loads(catalog_path.read_text())
        tile = catalog['tiles'][0]
        tile_path = self.root / 'a' / tile['file']
        payload = json.loads(tile_path.read_text())
        with closing(sqlite3.connect(directory / 'objects.sqlite')) as database:
            original = database.execute('''SELECT role,geometry_wkb,area_m2,length_m,district_id,
                attribute_status,overlap_count FROM objects''').fetchone()
        feature = payload['features'][0]
        feature['geometry'] = mapping(box(0, 0, 1, 1))
        with self.assertRaises(source.TopographyDataError):
            verification.compare(feature, original, scene.ORIGIN)
        payload = json.loads(tile_path.read_text())
        payload['features'].append(payload['features'][0])
        raw = (source.canonical(payload) + '\n').encode()
        tile_path.write_bytes(raw)
        tile.update({'count': 2, 'bytes': len(raw), 'sha256': source.digest(raw)})
        raw = (source.canonical(catalog) + '\n').encode()
        catalog_path.write_bytes(raw)
        summary_path = self.root / 'a/summary.json'
        summary = json.loads(summary_path.read_text())
        summary['catalog'] = {'bytes': len(raw), 'sha256': source.digest(raw)}
        summary_path.write_text(source.canonical(summary))
        with self.assertRaises(source.TopographyDataError):
            verification.verify(self.root / 'a', directory)

    def test_missing_attributes_cannot_silently_drop_an_object(self):
        directory, boundaries, _, _ = self.inputs()
        with closing(sqlite3.connect(directory / 'objects.sqlite')) as database:
            database.execute('DELETE FROM attribute_variants')
            database.commit()
        summary_path = directory / 'summary.json'
        summary = json.loads(summary_path.read_text())
        summary['objectsSha256'] = source.digest((directory / 'objects.sqlite').read_bytes())
        summary_path.write_text(source.canonical(summary))
        with self.assertRaises(source.TopographyDataError):
            scene.build(directory, boundaries, self.root / 'a')
        self.assertFalse((self.root / 'a').exists())

    def test_changed_objects_or_boundaries_cannot_produce_a_scene(self):
        directory, boundaries, _, _ = self.inputs()
        boundaries['districts'][0]['id'] = '11140'
        with self.assertRaises(source.TopographyDataError):
            scene.build(directory, boundaries, self.root / 'a')
        self.assertFalse((self.root / 'a').exists())
        with (directory / 'objects.sqlite').open('ab') as stream:
            stream.write(b'changed')
        with self.assertRaises(source.TopographyDataError):
            scene.build(directory, boundaries, self.root / 'a')

    def test_non_applicable_source_measures_remain_missing_instead_of_zero(self):
        geometry = LineString([(198100, 552000), (198110, 552010)])
        raw = shapely.to_wkb(geometry)
        feature, _ = scene.display_record('road', 'ROAD_CENTERLINE', raw, None, geometry.length,
                                          '11110', 'CONSISTENT', 0, {})
        record = ('ROAD_CENTERLINE', raw, None, geometry.length, '11110', 'CONSISTENT', 0)
        self.assertIsNone(feature['sourceAreaM2'])
        verification.compare(feature, record, scene.ORIGIN)
        feature['sourceAreaM2'] = 0
        with self.assertRaises(source.TopographyDataError):
            verification.compare(feature, record, scene.ORIGIN)


if __name__ == '__main__':
    unittest.main()
