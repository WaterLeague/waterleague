from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
from types import SimpleNamespace
import unittest

import shapely
from shapely.geometry import MultiPolygon, Polygon, box, mapping

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import prepare_seoul_topography as source
import prepare_topography_objects as objects
import prepare_topography_sites as sites
import verify_topography_sites as verification
import verify_topography_site_engine as engine_verification


class TopographySitesTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()

    def inputs(self, records, extra=()):
        directory = self.root / 'objects'
        directory.mkdir()
        spatial = self.root / 'spatial.sqlite'
        boundaries = {'districts': [{'id': '11110', 'nativeGeometry': mapping(box(-10, -10, 100, 100))}]}
        with closing(sqlite3.connect(spatial)) as native, closing(sqlite3.connect(directory / 'objects.sqlite')) as target:
            native.executescript('''CREATE TABLE layers(tile TEXT,layer TEXT,role TEXT,scale_denominator INTEGER);
                CREATE TABLE features(fid INTEGER,tile TEXT,layer TEXT,geometry_status TEXT,geometry_wkb BLOB,
                    minx REAL,miny REAL,maxx REAL,maxy REAL,deleted INTEGER);''')
            objects.prepare_database(target)
            for index, (role, geometry, props, overlap) in enumerate(records, 1):
                layer = 'layer' + str(index)
                identifier = objects.object_key(layer, geometry)
                target.execute('''INSERT INTO objects(object_id,layer,role,representative_fid,geometry_wkb,area_m2,
                    district_id,district_intersections,overlap_count) VALUES(?,?,?,?,?,?,?,?,?)''',
                    (identifier, layer, role, index, shapely.to_wkb(geometry), geometry.area, '11110', '[]', overlap))
                raw = source.canonical(props)
                target.execute('INSERT INTO attribute_variants VALUES(?,?,?)', (identifier, source.digest(raw.encode()), raw))
            for index, (role, geometry, props, overlap) in enumerate([*records, *extra], 1):
                native.execute('INSERT INTO layers VALUES(?,?,?,?)', ('tile', 'layer' + str(index), role, 1000))
                status = props.get('status', 'VALID')
                native.execute('INSERT INTO features VALUES(?,?,?,?,?,?,?,?,?,?)',
                    (index, 'tile', 'layer' + str(index), status, shapely.to_wkb(geometry) if status == 'VALID' else None,
                     *geometry.bounds, 0))
            target.commit()
            native.commit()
        spatial_hash = source.digest(spatial.read_bytes())
        report = {'objectsSha256': source.digest((directory / 'objects.sqlite').read_bytes()),
            'sourceSpatialSha256': spatial_hash, 'boundaryContentSha256': source.digest(source.canonical(boundaries).encode())}
        (directory / 'summary.json').write_text(source.canonical(report))
        return directory, SimpleNamespace(database=spatial, summary={'spatialSha256': spatial_hash}), boundaries

    def test_roof_holes_and_multiple_parts_remain_whole_and_kind_overlap_are_excluded(self):
        geometry = MultiPolygon([Polygon(box(0, 0, 10, 10).exterior.coords,
                                         [box(2, 2, 8, 8).exterior.coords]), box(20, 0, 22, 2)])
        records = [('BUILDING_FOOTPRINT', geometry, {'종류': '일반주택'}, 0),
                   ('BUILDING_FOOTPRINT', box(30, 0, 40, 10), {'종류': '무벽건물'}, 0),
                   ('BUILDING_FOOTPRINT', box(50, 0, 60, 10), {'종류': '아파트'}, 1)]
        directory, native, boundaries = self.inputs(records)
        report = sites.build(directory, native, boundaries, self.root / 'result')
        self.assertEqual(report['counts']['ROOF'], 1)
        self.assertEqual(report['counts']['ROOF_NOT_CONFIRMED_KIND'], 1)
        self.assertEqual(report['counts']['UNRESOLVED_BUILDING_OVERLAP'], 1)
        with closing(sqlite3.connect(self.root / 'result/sites.sqlite')) as database:
            raw, area, limit, removed = database.execute('SELECT geometry_wkb,area_m2,max_area_m2,removed_area_m2 FROM candidates').fetchone()
            self.assertEqual(raw, shapely.to_wkb(geometry))
            self.assertEqual((area, limit, removed), (68, '68.00', 0))
        self.assertFalse(report['policy']['roofKindIsStructuralApproval'])
        self.assertFalse(report['policy']['facilityAndCostBindingComplete'])

    def test_ground_masking_removes_building_and_water_preserves_hole_and_area_accounting(self):
        parent = box(0, 0, 20, 20)
        records = [('ROAD_AREA', parent, {}, 0)]
        extra = [('BUILDING_FOOTPRINT', box(2, 2, 8, 8), {}, 0),
                 ('RIVER_WATER_AREA', box(10, 0, 12, 20), {}, 0)]
        directory, native, boundaries = self.inputs(records, extra)
        sites.build(directory, native, boundaries, self.root / 'result')
        with closing(sqlite3.connect(self.root / 'result/sites.sqlite')) as database:
            raw, area, original, removed = database.execute('SELECT geometry_wkb,area_m2,source_area_m2,removed_area_m2 FROM candidates').fetchone()
            geometry = shapely.from_wkb(raw)
            self.assertEqual((area, original, removed), (324, 400, 76))
            self.assertTrue(parent.covers(geometry))
            self.assertEqual(sum(len(p.interiors) for p in geometry.geoms), 1)
            for _, obstacle, _, _ in extra:
                self.assertEqual(geometry.intersection(obstacle).area, 0)
            self.assertEqual(database.execute('SELECT COUNT(*) FROM exclusions').fetchone()[0], 2)

    def test_sidewalk_precedence_prevents_road_and_landscape_area_double_allocation(self):
        records = [('ROAD_AREA', box(0, 0, 20, 10), {}, 0),
                   ('SIDEWALK_AREA', box(5, 0, 10, 10), {}, 0),
                   ('CULTIVATION_LANDSCAPE_AREA', box(10, 0, 30, 10), {}, 0)]
        directory, native, boundaries = self.inputs(records)
        report = sites.build(directory, native, boundaries, self.root / 'result')
        self.assertEqual(report['counts']['GROUND'], 3)
        with closing(sqlite3.connect(self.root / 'result/sites.sqlite')) as database:
            rows = database.execute('SELECT role,geometry_wkb FROM candidates').fetchall()
            shapes = {role: shapely.from_wkb(raw) for role, raw in rows}
            self.assertEqual(shapes['SIDEWALK_AREA'].area, 50)
            self.assertEqual(shapes['ROAD_AREA'].area, 150)
            self.assertEqual(shapes['CULTIVATION_LANDSCAPE_AREA'].area, 100)
            self.assertEqual(sum(g.area for g in shapes.values()), shapely.union_all(list(shapes.values())).area)

    def test_invalid_ground_source_envelope_blocks_affected_region_without_repair(self):
        records = [('ROAD_AREA', box(0, 0, 10, 10), {}, 0)]
        extra = [('SIDEWALK_AREA', box(5, 5, 6, 6), {'status': 'INVALID'}, 0)]
        directory, native, boundaries = self.inputs(records, extra)
        report = sites.build(directory, native, boundaries, self.root / 'result')
        self.assertEqual(report['counts']['INVALID_MASK_INFLUENCE'], 1)
        self.assertEqual(report['counts'].get('CANDIDATE', 0), 0)

    def test_district_membership_does_not_clip_the_candidate_or_exterior_inflow_domain(self):
        records = [('BUILDING_FOOTPRINT', box(90, 90, 110, 110), {'종류': '일반주택'}, 0)]
        directory, native, boundaries = self.inputs(records)
        sites.build(directory, native, boundaries, self.root / 'result')
        with closing(sqlite3.connect(self.root / 'result/sites.sqlite')) as database:
            self.assertEqual(database.execute('SELECT area_m2,district_id FROM candidates').fetchone(), (400, '11110'))

    def test_full_fixture_reproduction_and_input_hash_guards(self):
        directory, native, boundaries = self.inputs([('ROAD_AREA', box(0, 0, 10, 10), {}, 0)])
        first = sites.build(directory, native, boundaries, self.root / 'a')
        second = sites.build(directory, native, boundaries, self.root / 'b')
        self.assertEqual(first, second)
        for name in ('sites.sqlite', 'summary.json'):
            self.assertEqual((self.root / 'a' / name).read_bytes(), (self.root / 'b' / name).read_bytes())
        checked = verification.verify(self.root / 'a', directory, native, boundaries=boundaries)
        self.assertEqual(checked['counts']['GROUND'], 1)
        self.assertEqual(checked['positiveAreaGroundOverlaps'], 0)
        with self.assertRaises(source.TopographyDataError):
            sites.build(directory, native, boundaries, self.root / 'a')
        boundaries['districts'][0]['id'] = '11140'
        with self.assertRaises(source.TopographyDataError):
            sites.build(directory, native, boundaries, self.root / 'c')
        self.assertFalse((self.root / 'c').exists())

    def test_full_comparison_rejects_consistently_rehashed_geometry_over_a_water_mask(self):
        parent = box(0, 0, 20, 20)
        directory, native, boundaries = self.inputs([('ROAD_AREA', parent, {}, 0)],
            [('RIVER_WATER_AREA', box(2, 2, 8, 8), {}, 0)])
        output = self.root / 'result'
        sites.build(directory, native, boundaries, output)
        self.assertEqual(verification.verify(output, directory, native, boundaries=boundaries)['counts']['holes'], 1)
        with closing(sqlite3.connect(output / 'sites.sqlite')) as database:
            object_id = database.execute('SELECT object_id FROM candidates').fetchone()[0]
            identifier, checksum = sites.candidate_key(object_id, parent)
            database.execute('''UPDATE candidates SET id=?,geometry_wkb=?,geometry_sha256=?,area_m2=400,
                max_area_m2='400.00',removed_area_m2=0''', (identifier, shapely.to_wkb(parent), checksum))
            database.commit()
        summary_path = output / 'summary.json'
        report = json.loads(summary_path.read_text())
        report['sitesSha256'] = source.digest((output / 'sites.sqlite').read_bytes())
        summary_path.write_text(source.canonical(report))
        with self.assertRaises(source.TopographyDataError):
            verification.verify(output, directory, native, boundaries=boundaries)

    def test_published_snapshot_binds_source_code_full_validation_and_unregistered_engine_cases(self):
        value = json.loads((source.ROOT / 'data/manifests/seoul-topography-sites-v1.json').read_text())
        self.assertEqual(value['generatorSha256'], source.digest(Path(sites.__file__).read_bytes()))
        self.assertEqual(value['geometryCodeSha256'], source.digest(Path(sites.site_geometry.__file__).read_bytes()))
        source_objects = json.loads((source.ROOT / value['sourceObjectsManifest']).read_text())
        self.assertEqual(value['sourceObjectsSha256'], source_objects['objectsSha256'])
        self.assertEqual(value['validation']['verifierSha256'], source.digest(Path(verification.__file__).read_bytes()))
        self.assertEqual(value['engineValidation']['verifierSha256'], source.digest(Path(engine_verification.__file__).read_bytes()))
        counts = value['counts']
        self.assertEqual(counts['CANDIDATE'], counts['ROOF'] + counts['GROUND'])
        self.assertEqual(counts['sourceRecords'], sum(n for key, n in counts.items() if key not in ('ROOF', 'GROUND', 'sourceRecords')))
        for kind in ('ROOF', 'GROUND'):
            self.assertEqual(value['validation']['counts'][kind], counts[kind])
        self.assertGreater(value['validation']['counts']['holes'], 0)
        self.assertGreater(value['validation']['counts']['multipart'], 0)
        self.assertFalse(value['serviceMigrated'])
        self.assertFalse(value['policy']['facilityAndCostBindingComplete'])
        self.assertFalse(value['engineValidation']['rankingEligible'])


if __name__ == '__main__':
    unittest.main()
