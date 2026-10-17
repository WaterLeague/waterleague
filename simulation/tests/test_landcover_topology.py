import json
import sys
import unittest
from pathlib import Path

from shapely.geometry import Polygon, box, mapping

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import diagnose_landcover_topology as topology


def feature(geometry, code='154'):
    return {'geometry': mapping(geometry), 'properties': {
        'L3_CODE': code, 'L3_NAME': '검사용 분류', 'IMG_DATE': '2023-12-31'}}


class LandcoverTopologyTests(unittest.TestCase):
    def test_crossing_keeps_source_and_compares_reproducible_candidates(self):
        inputs = [feature(Polygon([(0, 0), (10, 10), (0, 10), (10, 0), (0, 0)]))]
        before = json.dumps(inputs)
        result = topology.diagnose(inputs, box(0, 0, 10, 10))
        self.assertEqual(json.dumps(inputs), before)
        self.assertEqual(result, topology.diagnose(inputs, box(0, 0, 10, 10)))
        self.assertFalse(result['modelEligible'])
        self.assertFalse(result['calibrationEligible'])
        self.assertEqual(result['status'], 'DIAGNOSTIC_ONLY')
        self.assertEqual(result['originalAudit']['study']['unionAreaM2'], 0)
        for method in topology.METHODS:
            candidate = result['methods'][method]
            self.assertEqual(candidate['audit']['study']['unionAreaM2'], 50)
            self.assertEqual(candidate['changedFeatures'][0]['fullCandidate']['type'], 'MultiPolygon')
        self.assertEqual(result['methodComparison']['studyUnionSymmetricDifferenceM2'], 0)

    def test_overlapping_holes_report_method_disagreement(self):
        geometry = Polygon(box(0, 0, 10, 10).exterior.coords,
                           [box(1, 1, 6, 6).exterior.coords, box(4, 4, 9, 9).exterior.coords])
        result = topology.diagnose([feature(geometry)], box(-1, -1, 30, 30))
        self.assertEqual(result['methods']['linework']['audit']['study']['unionAreaM2'], 58)
        self.assertEqual(result['methods']['structure']['audit']['study']['unionAreaM2'], 54)
        self.assertEqual(result['methodComparison']['classStudySymmetricDifferenceM2']['154'], 4)
        self.assertEqual(result['methodComparison']['studyUnionSymmetricDifferenceM2'], 4)
        self.assertFalse(result['methodComparison']['features'][0]['sameAreaGeometry'])

    def test_collapsed_lines_are_reported_without_fabricated_area(self):
        geometry = Polygon([(0, 0), (1, 1), (1, 2), (1, 1), (0, 0)])
        result = topology.diagnose([feature(geometry)], box(-1, -1, 3, 3))
        for method in topology.METHODS:
            candidate = result['methods'][method]
            detail = candidate['changedFeatures'][0]
            self.assertTrue(detail['areaCandidate']['empty'])
            self.assertGreater(detail['fullCandidate']['nonAreaLengthM'], 0)
            self.assertTrue(detail['fullCandidate']['nonAreaComponentCounts'])
            self.assertEqual(candidate['audit']['study']['unionAreaM2'], 0)

    def test_valid_input_preserves_overlap_and_class_areas(self):
        inputs = [feature(box(0, 0, 6, 10)), feature(box(4, 0, 8, 10), '131')]
        result = topology.diagnose(inputs, box(0, 0, 10, 10))
        for method in topology.METHODS:
            candidate = result['methods'][method]
            self.assertEqual(candidate['unchangedOriginalValidFeatureCount'], 2)
            self.assertEqual(candidate['changedFeatures'], [])
            self.assertEqual(candidate['classUnionAreasM2'], {'131': 40, '154': 60})
            self.assertEqual(candidate['audit']['study']['overlapAreaM2'], 20)
            self.assertEqual(candidate['audit']['study']['uncoveredAreaM2'], 20)

    def test_outside_invalid_geometry_does_not_change_study_coverage(self):
        inputs = [feature(box(0, 0, 10, 10)), feature(Polygon(
            [(20, 0), (30, 10), (20, 10), (30, 0), (20, 0)]))]
        result = topology.diagnose(inputs, box(0, 0, 10, 10))
        for method in topology.METHODS:
            candidate = result['methods'][method]
            self.assertEqual(candidate['audit']['study']['coveredFraction'], 1)
            self.assertEqual(candidate['changedFeatures'][0]['studyAreaM2'], 0)

    def test_invalid_boundary_and_3d_geometry_are_rejected(self):
        with self.assertRaises(topology.audit.SpatialDataError):
            topology.diagnose([], Polygon())
        with self.assertRaises(topology.audit.SpatialDataError):
            topology.diagnose([feature(Polygon([(0, 0, 1), (1, 1, 2), (0, 1, 3)]))],
                              box(0, 0, 10, 10))


if __name__ == '__main__':
    unittest.main()
