"""합성 평면과 격자로 보간·외삽·누락 자료 처리 검증."""
import copy
import hashlib
import json
import math
import sys
import unittest
from pathlib import Path

from shapely.geometry import LineString, Point, mapping

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts'))
import audit_terrain_support as terrain
from audit_spatial_sources import SpatialDataError


class TerrainSupportTests(unittest.TestCase):
    @staticmethod
    def plane():
        return [{'id': str(i), 'coordinates': [x, y], 'value': 2*x-3*y+7}
                for i, (x, y) in enumerate([(0, 0), (10, 0), (0, 10), (10, 10), (4, 3)])]

    def test_linear_plane_vertices_edges_interior_and_input_order(self):
        points = self.plane()
        original = copy.deepcopy(points)
        tin = terrain.LinearTin(points)
        self.assertEqual(tin.describe(), terrain.LinearTin(list(reversed(points))).describe())
        for xy in ([0, 0], [10, 10], [4, 3], [5, 0], [0, 5], [1.3, 6.2], [7.7, 8.8]):
            sampled = tin.sample(xy)
            self.assertAlmostEqual(sampled['rawValue'], 2*xy[0]-3*xy[1]+7, places=12)
            self.assertAlmostEqual(sum(sampled['weights']), 1)
            self.assertEqual(len(sampled['pointIds']), 3)
        self.assertEqual(points, original)

    def test_outside_hull_is_never_extrapolated(self):
        tin = terrain.LinearTin(self.plane())
        for xy in ([-1e-14, 5], [5, 10+1e-12], [50, 50]):
            self.assertIsNone(tin.sample(xy))
        with self.assertRaises(SpatialDataError):
            tin.sample([math.inf, 0])

    def test_duplicate_collinear_and_nonfinite_points_rejected(self):
        points = self.plane()
        cases = [points+[{**points[0], 'id': 'new'}], points+[{**points[0], 'id': 'new', 'value': 500}],
                 points+[{**points[0], 'coordinates': [12, 12]}],
                 [{**p, 'value': float('nan')} if i == 0 else p for i, p in enumerate(points)],
                 [{'id': str(i), 'coordinates': [i, i], 'value': i} for i in range(4)]]
        for case in cases:
            with self.subTest(case=case), self.assertRaises(SpatialDataError):
                terrain.LinearTin(case)

    def test_grid_pixel_edges_nodata_and_outside(self):
        report = {'geoTransform': [100, 10, 0, 200, 0, -10], 'size': [2, 2], 'noDataValue': -9999}
        rows = [(105, 195, 1), (115, 195, 2), (105, 185, -9999), (115, 185, float('nan'))]
        self.assertEqual(terrain.sample_grid(report, rows, [100, 200])['rawValue'], 1)
        self.assertEqual(terrain.sample_grid(report, rows, [110, 195])['column'], 1)
        self.assertEqual(terrain.sample_grid(report, rows, [105, 190])['status'], 'NODATA')
        self.assertEqual(terrain.sample_grid(report, rows, [115, 185])['status'], 'NODATA')
        for xy in ([120, 195], [105, 180], [99, 195], [105, 201]):
            self.assertEqual(terrain.sample_grid(report, rows, xy)['status'], 'OUTSIDE_GRID')
        for invalid in ([*rows[1:], rows[0]], rows[:-1]):
            with self.assertRaises(SpatialDataError):
                terrain.sample_grid(report, invalid, [105, 195])
        with self.assertRaises(SpatialDataError):
            terrain.sample_grid({**report, 'geoTransform': [100, 10, .1, 200, 0, -10]}, rows, [105, 195])

    def test_source_properties_preserved_and_layer_fields_separated(self):
        point = {'geometry': mapping(Point(100, 200)), 'properties': {'UFID': 'a', '수치': 30.653}}
        line = {'geometry': mapping(LineString([(0, 0), (2, 2)])),
                'properties': {'UFID': 'b', '등고수치': 15.0, '구분': '계곡선'}}
        self.assertEqual(terrain.feature_records([point], 'points', 'tile')[0]['value'], 30.653)
        result = terrain.feature_records([line], 'contours', 'tile')[0]
        self.assertEqual(result['properties'], line['properties'])
        self.assertEqual(result['value'], 15.0)
        invalid = copy.deepcopy(point)
        invalid['geometry'] = mapping(Point(100, 200, 3))
        for features, kind in (([point, point], 'points'), ([invalid], 'points'), ([point], 'contours')):
            with self.assertRaises(SpatialDataError):
                terrain.feature_records(features, kind, 'tile')

    def test_missing_comparisons_are_not_zeros_or_accuracy_metrics(self):
        result = terrain.comparison_stats([{'demMinusReferenceRawValue': x} for x in (-18.7, 2, None)])
        self.assertEqual(result['comparedCount'], 2)
        self.assertEqual(result['missingCount'], 1)
        self.assertEqual(result['absoluteRawDifference']['max'], 18.7)
        self.assertEqual(result['unitCompatibility'], 'UNVERIFIED')
        self.assertFalse(result['accuracyMetric'])

    def test_published_summary_is_linked_without_source_coordinates(self):
        path = ROOT/'data/manifests/seongsu-terrain-support.json'
        raw = path.read_bytes()
        self.assertEqual(raw, (ROOT/'frontend/public/data/seongsu-terrain-support.json').read_bytes())
        report = json.loads(raw)
        self.assertFalse(report['modelEligible'])
        self.assertEqual(report['summary']['sourcePointCount'], 12)
        self.assertEqual(report['summary']['pointsWithinStudy'], 1)
        self.assertEqual(report['summary']['contoursIntersectingStudy'], 0)
        self.assertEqual([d['year'] for d in report['datasets']], [2024, 2025])
        for name, expected in report['codeHashes'].items():
            self.assertEqual(hashlib.sha256((ROOT/'scripts'/name).read_bytes()).hexdigest(), expected)
        for key in ('coordinates', 'geometry', 'cellCenter', 'pointValues', 'pointFeatures', 'samples'):
            self.assertNotIn('"'+key+'"', raw.decode())
        for dataset in report['datasets']:
            self.assertEqual(dataset['resolutionM'], [90, 90])
            self.assertEqual(dataset['comparison']['points']['comparedCount'], 12)
            self.assertIsNone(dataset['verticalDatum'])
            self.assertIsNone(dataset['bandUnit'])
