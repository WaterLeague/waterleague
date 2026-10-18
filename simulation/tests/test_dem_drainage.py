"""지형 하향 경로·외부 기여·미해결 경계와 원 높이 보존 검사."""
from copy import deepcopy
import unittest

from pyproj import CRS

from waterleague_sim.engine.flood_errors import FloodModelError
from waterleague_sim.terrain.drainage import analyze, window_context


def grid(values=None, dx=1, dy=1):
    return {'width': 5, 'height': 5, 'values': values or [20 - r for r in range(5) for _ in range(5)],
        'geoTransform': [0, dx, 0, 0, 0, -dy], 'coordinateWkt': CRS.from_epsg(5186).to_wkt(),
        'noDataValue': -9999, 'sourceFiles': {'analytical-test': 'a' * 64},
        'verticalReference': {'unit': 'm', 'unitStatus': 'SOURCE_CONFIRMED',
                              'unitEvidence': '합성 해석 검사'}}


class DemDrainageTests(unittest.TestCase):
    def test_planar_flow_accumulation_and_outside_window(self):
        source = grid()
        before = deepcopy(source)
        result = analyze(source)
        self.assertEqual(source, before)
        self.assertEqual(result, analyze(source))
        self.assertEqual(result['successorCell'][12], 17)
        self.assertEqual(result['contributingCellsIncludingSelf'][22], 4)
        self.assertEqual(result['terminalCell'][7], 22)
        self.assertEqual(result['summary']['terminalContributingCells'], 25)
        context = window_context(source, result, [2, 2, 1, 2])
        self.assertEqual(context['incomingLinks'], [[7, 12]])
        self.assertEqual(context['outgoingLinks'], [[17, 22]])
        self.assertEqual(context['outsideContributingCells'], [7])
        self.assertEqual(context['outsideContributingAreaM2'], 1)
        self.assertFalse(context['hydraulicBoundaryAdmissible'])

    def test_metric_distance_changes_downhill_selection(self):
        values = [100.] * 25
        values[12], values[13], values[17], values[18] = 10, 9, 8, 7
        self.assertEqual(analyze(grid(values))['successorCell'][12], 18)
        self.assertEqual(analyze(grid(values, dx=10))['successorCell'][12], 17)

    def test_pits_flats_equal_slopes_and_missing_neighbors_are_not_invented_outlets(self):
        for kind in ('pit', 'flat', 'tie', 'nodata'):
            values = [20.] * 25
            values[12] = 10
            expected = 'DEPRESSION_UNRESOLVED'
            if kind == 'flat':
                values[13], expected = 10, 'FLAT_UNRESOLVED'
            elif kind == 'tie':
                values[11] = values[13] = 9
                expected = 'EQUAL_SLOPE_UNRESOLVED'
            elif kind == 'nodata':
                values[13], expected = -9999, 'NODATA_NEIGHBOR_UNRESOLVED'
            with self.subTest(kind=kind):
                result = analyze(grid(values))
                self.assertEqual(result['status'][12], expected)
                self.assertIsNone(result['successorCell'][12])
                self.assertEqual(result['status'][0], 'TILE_EDGE_UNRESOLVED')
                self.assertEqual(result['summary']['terminalContributingCells'], 24 if kind == 'nodata' else 25)

    def test_source_window_and_metric_reference_are_required(self):
        source = grid()
        result = analyze(source)
        source['values'][12] += .1
        with self.assertRaisesRegex(FloodModelError, 'GRID_BINDING'):
            window_context(source, result, [2, 2, 1, 1])
        for change in ({'coordinateWkt': CRS.from_epsg(4326).to_wkt()},
                       {'geoTransform': [0, 1, .1, 0, 0, -1]}, {'values': [float('nan')] * 25}):
            with self.subTest(change=list(change)), self.assertRaises(FloodModelError):
                analyze(grid() | change)
        with self.assertRaisesRegex(FloodModelError, 'WINDOW_INVALID'):
            window_context(grid(), result, [4, 4, 2, 2])


if __name__ == '__main__':
    unittest.main()
