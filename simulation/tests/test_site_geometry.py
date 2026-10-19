import copy
import unittest

from shapely.geometry import MultiPolygon, Polygon, box, mapping

from waterleague_sim.spatial.geometry import SiteGeometryError, area_limit, cell_geometry, dimensions, polygon_geometry


class SiteGeometryTests(unittest.TestCase):
    def test_holes_and_multiple_parts_determine_area_and_runoff_width(self):
        first = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)],
                        [[(2, 2), (8, 2), (8, 8), (2, 8)]])
        original = MultiPolygon([first, box(20, 0, 22, 2)])
        value = mapping(original)
        decoded = cell_geometry({'geometry': value, 'areaM2': 68})
        self.assertTrue(decoded.equals_exact(original, 0))
        self.assertEqual(dimensions(decoded)['flowLengthM'], 22)
        self.assertEqual(dimensions(decoded)['runoffWidthM'], 68 / 22)
        self.assertEqual(area_limit(decoded), 68)
        with self.assertRaises(SiteGeometryError):
            cell_geometry({'geometry': value, 'areaM2': 104})

    def test_invalid_geometry_is_not_closed_repaired_or_replaced_by_outer_ring(self):
        invalid = [
            {'type': 'Polygon', 'coordinates': [[[0, 0], [10, 0], [10, 10], [0, 10]]]},
            {'type': 'Polygon', 'coordinates': [[[0, 0], [10, 10], [0, 10], [10, 0], [0, 0]]]},
            mapping(Polygon(box(0, 0, 10, 10).exterior.coords, [box(12, 12, 13, 13).exterior.coords])),
            mapping(MultiPolygon([box(0, 0, 10, 10), box(1, 1, 2, 2)])),
            {'type': 'Point', 'coordinates': [0, 0]}, None,
        ]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(SiteGeometryError):
                cell_geometry({'geometry': value, 'coordinates': list(box(0, 0, 1, 1).exterior.coords), 'areaM2': 1})

    def test_non_finite_boolean_and_three_dimensional_coordinates_are_rejected(self):
        for point in [(True, 0), (float('nan'), 0), (0, float('inf')), (0, 0, 1)]:
            value = {'type': 'Polygon', 'coordinates': [[point, (10, 0), (10, 10), (0, 10), point]]}
            with self.subTest(point=point), self.assertRaises(SiteGeometryError):
                polygon_geometry(value)

    def test_historical_single_ring_and_cent_limit_do_not_mutate_source(self):
        cell = {'coordinates': list(box(0, 0, 3.456, 1).exterior.coords), 'areaM2': 3.456}
        before = copy.deepcopy(cell)
        self.assertEqual(str(area_limit(cell_geometry(cell))), '3.45')
        self.assertEqual(cell, before)
