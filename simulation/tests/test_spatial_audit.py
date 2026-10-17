import hashlib
import json
import stat
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from pyproj import CRS
from shapely.geometry import Polygon, box, mapping

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import audit_spatial_sources as audit


class SpatialAuditTests(unittest.TestCase):
    def test_archive_preserves_hash_and_checks_crc(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'source.zip'
            with zipfile.ZipFile(source, 'w') as archive:
                archive.writestr('37705/', '')
                archive.writestr('37705/test.img', b'public-test-input')
            result = audit.extract_checked(source, root / 'out', audit.digest(source))
            self.assertEqual((root / 'out/37705/test.img').read_bytes(), b'public-test-input')
            self.assertEqual(result['members'][0]['sha256'], hashlib.sha256(b'public-test-input').hexdigest())
            with self.assertRaises(audit.SpatialDataError):
                audit.extract_checked(source, root / 'wrong', '0'*64)
            broken = source.read_bytes().replace(b'public-test-input', b'broken-test-input')
            source.write_bytes(broken)
            with self.assertRaisesRegex(audit.SpatialDataError, 'CRC'):
                audit.extract_checked(source, root / 'broken')

    def test_archive_rejects_traversal_links_and_normalized_duplicates(self):
        cases = [('../outside', None), ('/absolute', None), ('C:/drive', None),
                 ('..\\outside', None), ('link', stat.S_IFLNK | 0o777)]
        for name, mode in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                source = root / 'source.zip'
                with zipfile.ZipFile(source, 'w') as archive:
                    info = zipfile.ZipInfo(name)
                    if mode:
                        info.external_attr = mode << 16
                    archive.writestr(info, 'target')
                with self.assertRaises(audit.SpatialDataError):
                    audit.extract_checked(source, root / 'out')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'source.zip'
            with zipfile.ZipFile(source, 'w') as archive:
                archive.writestr('가.img', 'one')
                archive.writestr('\u1100\u1161.img', 'two')
            with self.assertRaises(audit.SpatialDataError):
                audit.extract_checked(source, root / 'out')

    def test_archive_does_not_overwrite_existing_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'source.zip'
            with zipfile.ZipFile(source, 'w') as archive:
                archive.writestr('test', 'input')
            output = root / 'out'
            output.mkdir()
            with self.assertRaises(FileExistsError):
                audit.extract_checked(source, output)

    def test_boundary_uses_original_crs_and_rejects_degree_area(self):
        crs = CRS.from_epsg(5186)
        boundary, evidence = audit.study_boundary(crs.to_wkt())
        self.assertGreater(boundary.area, 73000)
        self.assertLess(boundary.area, 74000)
        self.assertEqual(evidence['identifiedEpsg'], 5186)
        self.assertEqual(evidence['originalWkt'], crs.to_wkt())
        self.assertIsNone(evidence['coordinateEpoch'])
        with self.assertRaises(audit.SpatialDataError):
            audit.study_boundary(CRS.from_epsg(4326).to_wkt())

    def test_dem_excludes_nodata_and_keeps_original_pixel_values(self):
        info = {'size': [2, 2], 'geoTransform': [0, 10, 0, 20, 0, -10],
                'bands': [{'type': 'Float32', 'noDataValue': -9999}],
                'coordinateSystem': {'wkt': 'test'}, 'driverShortName': 'HFA'}
        with patch.object(audit, 'command', side_effect=[json.dumps(info),
                '5 15 1\n15 15 -9999\n5 5 3\n15 5 5\n']), patch.object(
                audit, 'study_boundary', return_value=(box(0, 0, 20, 20), {})):
            report, rows = audit.dem(Path('test.img'))
        self.assertEqual(len(rows), 4)
        self.assertEqual(report['study']['intersectingCellCount'], 4)
        self.assertEqual(report['study']['validFraction'], .75)
        self.assertEqual(report['study']['rawValues'], {'count': 3, 'min': 1, 'max': 5, 'mean': 3})
        self.assertIsNone(report['study']['cells'][1]['value'])
        self.assertIsNone(report['verticalDatum'])

    def feature(self, geometry, code='154'):
        return {'geometry': mapping(geometry), 'properties': {
            'L3_CODE': code, 'L3_NAME': '도로', 'IMG_DATE': '2023-12-31'}}

    def test_landcover_separates_overlap_gap_and_invalid_geometry(self):
        features = [self.feature(box(0, 0, 6, 10)), self.feature(box(4, 0, 8, 10)),
                    self.feature(Polygon([(8, 0), (10, 10), (8, 10), (10, 0), (8, 0)]))]
        before = json.dumps(features)
        report = audit.analyze_landcover(features, box(0, 0, 10, 10))
        self.assertEqual(report['studyGeometryStatus'], 'INCOMPLETE_INVALID_GEOMETRY')
        self.assertEqual(len(report['invalidStudyEnvelopeCandidates']), 1)
        self.assertEqual(report['study']['summedAreaM2'], 100)
        self.assertEqual(report['study']['unionAreaM2'], 80)
        self.assertEqual(report['study']['overlapAreaM2'], 20)
        self.assertEqual(report['study']['uncoveredAreaM2'], 20)
        self.assertTrue(report['study']['validGeometriesOnly'])
        self.assertEqual(report['imageDateCounts'], {'2023-12-31': 3})
        self.assertEqual(before, json.dumps(features))

    def test_invalid_outside_study_does_not_become_regional_area(self):
        report = audit.analyze_landcover([
            self.feature(Polygon([(20, 0), (30, 10), (20, 10), (30, 0), (20, 0)])),
            self.feature(box(0, 0, 10, 10))], box(0, 0, 10, 10))
        self.assertEqual(report['invalidStudyEnvelopeCandidates'], [])
        self.assertEqual(sum(report['invalidGeometries'].values()), 1)
        self.assertEqual(report['study']['coveredFraction'], 1)


if __name__ == '__main__':
    unittest.main()
