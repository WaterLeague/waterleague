import sys
import unittest
from pathlib import Path

import pyproj
import shapely
from shapely.geometry import Polygon, box, mapping

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import audit_spatial_sources as audit
from prepare_topography_buildings import normalize


class TopographyBuildingsTests(unittest.TestCase):
    def setUp(self):
        self.transformer = pyproj.Transformer.from_crs(4326, 5186, always_xy=True)
        self.boundary = shapely.transform(box(127.053, 37.543, 127.055, 37.545),
                                         self.transformer.transform, interleaved=False)

    def feature(self, geometry, floors=3, identifier='test', name='시험 건물'):
        return {'geometry': mapping(geometry), 'properties': {
            'UFID': identifier, '명칭': name, '층수': floors}}

    def test_reprojection_preserves_holes_and_original_footprint(self):
        geographic = Polygon([(127.0529, 37.544), (127.0545, 37.544),
                              (127.0545, 37.5445), (127.0529, 37.5445)],
                             holes=[[(127.054, 37.5441), (127.0542, 37.5441),
                                     (127.0542, 37.5443), (127.054, 37.5443)]])
        native = shapely.transform(geographic, self.transformer.transform, interleaved=False)
        result = normalize([self.feature(native)], self.boundary, self.transformer, '377052201')
        self.assertEqual(result[0]['id'], '377052201:test')
        self.assertEqual(result[0]['aboveGroundFloors'], 3)
        self.assertEqual(result[0]['name'], '시험 건물')
        polygons = result[0]['polygons']
        self.assertEqual(len(polygons[0]), 2)
        restored = Polygon(polygons[0][0], polygons[0][1:])
        self.assertLess(restored.hausdorff_distance(geographic), 1e-10)
        self.assertLess(restored.bounds[0], 127.053)

    def test_touching_and_outside_features_are_excluded(self):
        boundary = box(204000, 549000, 204100, 549100)
        features = [self.feature(box(204100, 549000, 204110, 549100)),
                    self.feature(box(204200, 549000, 204210, 549100))]
        self.assertEqual(normalize(features, boundary, self.transformer, 'test'), [])

    def test_floor_unknown_and_duplicate_or_invalid_metadata_rejection(self):
        point = self.boundary.centroid
        geometry = box(point.x, point.y, point.x+5, point.y+5)
        for floors in [None, 0]:
            self.assertIsNone(normalize([self.feature(geometry, floors)], self.boundary,
                                       self.transformer, 'tile')[0]['aboveGroundFloors'])
        for floors in [-1, 201, 1.5, True, '3']:
            with self.subTest(floors=floors), self.assertRaises(audit.SpatialDataError):
                normalize([self.feature(geometry, floors)], self.boundary, self.transformer, 'tile')
        for features in [[self.feature(geometry), self.feature(geometry)],
                         [self.feature(geometry, name='한\ufffd글')],
                         [self.feature(geometry, identifier='../bad')]]:
            with self.assertRaises(audit.SpatialDataError):
                normalize(features, self.boundary, self.transformer, 'tile')

    def test_invalid_or_3d_geometry_is_not_silently_repaired(self):
        point = self.boundary.centroid
        x, y = point.x, point.y
        for geometry in [Polygon([(x,y),(x+5,y+5),(x+5,y),(x,y+5)]),
                         Polygon([(x,y,0),(x+5,y,0),(x+5,y+5,0)])]:
            with self.assertRaises(audit.SpatialDataError):
                normalize([self.feature(geometry)], self.boundary, self.transformer, 'tile')
