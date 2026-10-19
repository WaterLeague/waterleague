from contextlib import closing
import json
import hashlib
import inspect
from pathlib import Path
import sqlite3
import unittest

from shapely.geometry import Polygon, box, mapping

import test_topography_sites as fixtures
import prepare_native_play_catalog as catalog
import verify_native_play_catalog as verification
from waterleague_sim.spatial import reference_conditions
from waterleague_sim.spatial.play_catalog import NativePlayCatalog, NativeCatalogError
from waterleague_sim.engine import continuous


class NativePlayCatalogTests(unittest.TestCase):
    def test_published_snapshot_binds_source_conditions_and_limits_the_validation_claim(self):
        root = catalog.source.ROOT
        report = json.loads((root / 'data/manifests/seoul-native-play-v1.json').read_text())
        for key, module in (
            ('generatorSha256', catalog), ('profileCodeSha256', catalog.playing_profile),
            ('referenceCodeSha256', reference_conditions), ('geometryCodeSha256', catalog.geometry_code),
            ('footprintCodeSha256', catalog.design_footprint), ('facilityCodeSha256', catalog.facilities),
            ('initializationCodeSha256', catalog.initialization)):
            self.assertEqual(report[key], hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest())
        self.assertEqual(report['sourceSitesSha256'], json.loads((root / 'data/manifests/seoul-topography-sites-v1.json').read_text())['sitesSha256'])
        self.assertEqual(report['sourceObjectsSha256'], json.loads((root / 'data/manifests/seoul-topography-objects-v1.json').read_text())['objectsSha256'])
        self.assertEqual(report['referenceScenario'], reference_conditions.reference())
        self.assertEqual(report['costSourceSha256'], hashlib.sha256(catalog.COST_PATH.read_bytes()).hexdigest())
        checked = report['validation']
        self.assertEqual(checked['playSha256'], report['playSha256'])
        self.assertEqual(checked['verifierSha256'], hashlib.sha256(Path(verification.__file__).read_bytes()).hexdigest())
        self.assertEqual(checked['readerSha256'], hashlib.sha256(Path(inspect.getfile(NativePlayCatalog)).read_bytes()).hexdigest())
        self.assertEqual(checked['counts'], report['counts'])
        self.assertEqual(checked['districtCount'], 25)
        self.assertEqual(len(report['districtKindCounts']), 50)
        self.assertEqual(sum(report['districtKindCounts'].values()), report['counts']['records'])
        self.assertTrue(checked['sourceGeometryWkbByteIdentical'])
        self.assertFalse(checked['localSoilSlopeMaterialConfirmed'])
        self.assertFalse(checked['constructionApproved'])
        self.assertFalse(checked['serviceMigrated'])
        engine = checked['engineValidation']
        self.assertFalse(engine['rankingEligible'])
        self.assertFalse(engine['antecedentSpinupApplied'])
        self.assertEqual({c['facilityType'] for c in engine['cases']}, set(catalog.playing_profile.FACILITY_ORDER))
        self.assertTrue(all(c['directRainVolumeMatched'] for c in engine['cases']))
        self.assertTrue(report['reproducibility']['databaseByteIdentical'])
        self.assertTrue(report['reproducibility']['summaryByteIdentical'])

    def inputs(self):
        fixture = fixtures.TopographySitesTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        roof = Polygon(box(0, 0, 10, 10).exterior.coords, [box(2, 2, 4, 4).exterior.coords])
        records = [('BUILDING_FOOTPRINT', roof, {'종류': '일반주택', '층수': '4'}, 0),
            ('ROAD_AREA', box(20, 0, 30, 10), {}, 0),
            ('CULTIVATION_LANDSCAPE_AREA', box(40, 0, 50, 10), {'구분': '밭'}, 0),
            ('CULTIVATION_LANDSCAPE_AREA', box(60, 0, 70, 10), {'구분': '논'}, 0)]
        directory, native, boundaries = fixture.inputs(records)
        sites = fixture.root / 'sites'
        fixtures.sites.build(directory, native, boundaries, sites)
        return fixture.root, sites, directory, roof

    def test_whole_source_and_cost_binding_is_reproducible_and_unsupported_shape_is_retained(self):
        root, sites, objects, roof = self.inputs()
        first = catalog.build(sites, objects, root / 'a')
        second = catalog.build(sites, objects, root / 'b')
        self.assertEqual(first, second)
        for name in ('play.sqlite', 'summary.json'):
            self.assertEqual((root / 'a' / name).read_bytes(), (root / 'b' / name).read_bytes())
        self.assertEqual(first['counts'], {'EXPLORATORY_REFERENCE_SCENARIO': 3,
            'UNSUPPORTED_SURFACE_PROCESS': 1, 'records': 4})
        self.assertEqual(set(first['facilityCounts']), set(catalog.playing_profile.FACILITY_ORDER))
        checked = verification.verify(root / 'a', sites, objects)
        self.assertTrue(checked['sourceGeometryWkbByteIdentical'])
        self.assertEqual(checked['counts']['records'], 4)
        with closing(catalog.connect(root / 'a/play.sqlite')) as db:
            settings = json.loads(db.execute("SELECT value FROM metadata WHERE key='catalog'").fetchone()[0])
            self.assertEqual(settings['referenceScenario'], reference_conditions.reference())
            self.assertEqual(settings['costSourceSha256'], catalog.COST_SHA256)
            self.assertEqual(settings['budget'], 2_000_000_000)
            self.assertFalse(settings['policy']['serviceMigrated'])
            cell = json.loads(db.execute("SELECT body FROM sites WHERE kind='ROOF'").fetchone()[0])
            self.assertEqual(cell['geometry'], json.loads(json.dumps(mapping(roof))))
            self.assertEqual(cell['areaM2'], roof.area)
            self.assertEqual(cell['physicalInputs']['geometrySourceIds'], cell['sourceIds'])
            unsupported, mask = db.execute("SELECT body,allowed_mask FROM sites WHERE status='UNSUPPORTED_SURFACE_PROCESS'").fetchone()
            self.assertEqual(json.loads(unsupported)['sourceLandUse'], '논')
            self.assertEqual(mask, 0)
            with self.assertRaises(sqlite3.OperationalError):
                db.execute('DELETE FROM sites')

    def test_replaced_input_and_existing_output_are_rejected(self):
        root, sites, objects, _ = self.inputs()
        catalog.build(sites, objects, root / 'a')
        with self.assertRaises(fixtures.source.TopographyDataError):
            catalog.build(sites, objects, root / 'a')
        with (sites / 'sites.sqlite').open('ab') as stream:
            stream.write(b'bad')
        with self.assertRaises(fixtures.source.TopographyDataError):
            catalog.build(sites, objects, root / 'b')
        self.assertFalse((root / 'b').exists())

    def test_full_comparison_rejects_changed_body_even_after_local_file_rehash(self):
        root, sites, objects, _ = self.inputs()
        report = catalog.build(sites, objects, root / 'a')
        with closing(sqlite3.connect(root / 'a/play.sqlite')) as database:
            database.execute("UPDATE sites SET body=json_set(body,'$.areaM2',97) WHERE kind='ROOF'")
            database.commit()
        report['playSha256'] = catalog.spatial.file_sha256(root / 'a/play.sqlite')
        (root / 'a/summary.json').write_text(json.dumps(report))
        with self.assertRaises(ValueError):
            verification.verify(root / 'a', sites, objects)

    def test_queries_use_the_full_polygon_and_reject_cross_district_or_excess_area(self):
        root, sites, objects, _ = self.inputs()
        report = catalog.build(sites, objects, root / 'a')
        reader = NativePlayCatalog(root / 'a/play.sqlite', report['playSha256'])
        self.assertEqual(reader.bounds([2.5, 2.5, 3.5, 3.5]), [])
        roof = reader.bounds([0, 0, 1, 1], district='11110', kind='ROOF')[0]
        self.assertEqual(roof['areaM2'], 96)
        placement = reader.placement(roof['id'], 'GREEN_ROOF', '96.00', district='11110')
        self.assertEqual(placement['costKrw'], '33600000.00')
        self.assertEqual(placement['catalogSha256'], report['playSha256'])
        for area in ('96.01', '0', '-1', '.001', 'NaN', True):
            with self.assertRaises(NativeCatalogError):
                reader.placement(roof['id'], 'GREEN_ROOF', area, district='11110')
        with self.assertRaises(NativeCatalogError):
            reader.require(roof['id'], '11140')
        with self.assertRaises(NativeCatalogError):
            reader.placement(roof['id'], 'RAIN_GARDEN', 1, district='11110')
        with self.assertRaises(NativeCatalogError):
            reader.bounds([0, 0, 100, 100], limit=1)
        for bounds in ([0, 0, 10000, 10000], [1, 0, 0, 1], [0, 0, float('nan'), 1]):
            with self.assertRaises(NativeCatalogError):
                reader.bounds(bounds)
        self.assertEqual(len(reader.bounds([60, 0, 70, 10])), 0)
        unsupported = reader.bounds([60, 0, 70, 10], include_unsupported=True)[0]
        with self.assertRaises(NativeCatalogError):
            reader.model(unsupported['id'], district='11110')
        model = reader.model(roof['id'], district='11110')
        model['rainfall'] = fixtures.engine_verification.native.read_json(
            fixtures.engine_verification.FORCING)['rainfall']
        self.assertIn(roof['id'], continuous.input_source(model, [placement], None))
        model['referenceScenario']['id'] = 'changed'
        self.assertEqual(reader.metadata()['referenceScenario'], reference_conditions.reference())
        with self.assertRaises(NativeCatalogError):
            NativePlayCatalog(root / 'a/play.sqlite', '0' * 64)
        (root / 'link').symlink_to(root / 'a/play.sqlite')
        with self.assertRaises(NativeCatalogError):
            NativePlayCatalog(root / 'link', report['playSha256'])


if __name__ == '__main__':
    unittest.main()
