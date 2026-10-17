import copy
import hashlib
import json
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pyproj
import shapely
from shapely.geometry import Polygon, box, mapping

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import audit_cell_landcover as cell_audit


def feature(geometry, code='154', name='도로'):
    return {'geometry': mapping(geometry), 'properties': {
        'L3_CODE': code, 'L3_NAME': name, 'IMG_DATE': '2023-12-31'}}


def cell(identifier, boundary):
    return {'id': identifier, 'kind': 'GROUND', 'boundary': boundary,
            'geometry': mapping(boundary), 'modelAreaM2': boundary.area,
            'nativeMinusModelAreaM2': 0}


class CellLandcoverTests(unittest.TestCase):
    def setUp(self):
        self.model = json.loads((cell_audit.audit.ROOT/'data/models/seongsu-lab.json').read_text())
        self.snapshot = json.loads((cell_audit.audit.ROOT/'frontend/public/data/seongsu.json').read_text())
        self.transformer = pyproj.Transformer.from_crs(4326, 5186, always_xy=True)

    def test_known_cells_keep_source_coordinates_and_distinguish_assumed_patch_area(self):
        before = copy.deepcopy([self.model, self.snapshot])
        cells = cell_audit.cell_boundaries(self.model, self.snapshot, self.transformer)
        self.assertEqual([self.model, self.snapshot], before)
        self.assertEqual(len(cells), 13)
        roofs = [c for c in cells if c['kind'] == 'ROOF']
        grounds = [c for c in cells if c['kind'] == 'GROUND']
        self.assertEqual(len(roofs), 8)
        self.assertEqual(len(grounds), 5)
        for c in roofs:
            self.assertEqual(round(c['wgs84GeodesicAreaM2'], 2), c['modelAreaM2'])
            self.assertEqual(c['coordinateSource']['route'], 'OSM_ORIGINAL_WGS84')
        for c in grounds:
            self.assertEqual(c['modelAreaM2'], 100)
            self.assertLess(c['nativeAreaM2'], 100)
            self.assertGreater(c['nativeAreaM2'], 99)
            self.assertFalse(c['coordinateSource']['surveyedBoundary'])

    def test_broken_original_display_and_model_area_bindings_fail(self):
        modifications = [('source', lambda m, s: m.update(geometrySourceHash='wrong')),
                         ('shape', lambda m, s: m['cells'][0]['coordinates'][0].__setitem__(0, 1)),
                         ('area', lambda m, s: m['cells'][0].update(areaM2=100)),
                         ('duplicate', lambda m, s: m['cells'].append(copy.deepcopy(m['cells'][0]))),
                         ('ground', lambda m, s: m['cells'][-1].update(areaEvidence='SURVEYED')),
                         ('origin', lambda m, s: s.update(origin=[True, 37.54]))]
        for name, modify in modifications:
            with self.subTest(name=name):
                m, s = copy.deepcopy([self.model, self.snapshot])
                modify(m, s)
                with self.assertRaises(cell_audit.audit.SpatialDataError):
                    cell_audit.cell_boundaries(m, s, self.transformer)
        building = next(b for b in self.snapshot['features'] if b['id'] == self.model['cells'][0]['buildingId'])
        building['geographicCoordinates'][0] = [127.054]
        with self.assertRaises(cell_audit.audit.SpatialDataError):
            cell_audit.cell_boundaries(self.model, self.snapshot, self.transformer)

    def test_union_overlap_gap_and_touch_are_independent(self):
        features = [feature(box(0,0,6,10)), feature(box(4,0,8,10), '131', '상업'),
                    feature(box(10,0,20,10))]
        before = copy.deepcopy(features)
        result = cell_audit.diagnose(features, [cell('G1', box(0,0,10,10))], box(0,0,10,10))
        self.assertEqual(features, before)
        for m in cell_audit.METHODS:
            value = result['cells'][0]['methods'][m]
            self.assertEqual(value['featureCount'], 2)
            self.assertEqual(value['sumAreaM2'], 100)
            self.assertEqual(value['unionAreaM2'], 80)
            self.assertEqual(value['overlapAreaM2'], 20)
            self.assertEqual(value['crossClassOverlapAreaM2'], 20)
            self.assertEqual(value['uncoveredAreaM2'], 20)
            self.assertEqual(value['coveredFraction'], .8)
        self.assertEqual(result, cell_audit.diagnose(features, [cell('G1', box(0,0,10,10))], box(0,0,10,10)))

    def test_disagreement_of_repaired_holes_is_preserved(self):
        geometry = Polygon(box(0,0,10,10).exterior.coords,
                           [box(1,1,6,6).exterior.coords, box(4,4,9,9).exterior.coords])
        result = cell_audit.diagnose([feature(geometry)], [cell('G1', box(0,0,10,10))], box(0,0,10,10))
        c = result['cells'][0]
        self.assertEqual(c['methods']['originalValidOnly']['unionAreaM2'], 0)
        self.assertEqual(c['methods']['linework']['unionAreaM2'], 58)
        self.assertEqual(c['methods']['structure']['unionAreaM2'], 54)
        self.assertEqual(c['methodComparison']['classSymmetricDifferenceM2']['154'], 4)
        self.assertFalse(result['modelEligible'])
        self.assertFalse(result['calibrationEligible'])

    def test_invalid_envelope_does_not_imply_positive_area_coverage(self):
        features = [feature(Polygon([(0,0),(10,10),(0,10),(10,0),(0,0)]))]
        result = cell_audit.diagnose(features, [cell('G1', box(0,4,1,6))], box(0,0,10,10))
        c = result['cells'][0]
        self.assertEqual(c['invalidEnvelopeIndexes'], [0])
        self.assertEqual(c['repairedPositiveAreaIndexes'], {'linework': [], 'structure': []})
        self.assertEqual(c['methods']['linework']['unionAreaM2'], 0)

    def test_collapsed_and_empty_cover_do_not_become_observed_zero(self):
        collapsed = Polygon([(0,0),(1,1),(1,2),(1,1),(0,0)])
        for features in [[], [feature(collapsed)]]:
            result = cell_audit.diagnose(features, [cell('G1', box(0,0,10,10))], box(0,0,10,10))
            for m in cell_audit.METHODS:
                self.assertEqual(result['cells'][0]['methods'][m]['uncoveredAreaM2'], 100)
        self.assertGreater(result['invalidSourceCandidates'][0]['methods']['linework']['full']['nonAreaLengthM'], 0)

    def test_cells_overlap_and_outside_study_are_reported(self):
        result = cell_audit.diagnose([], [cell('G1', box(0,0,10,10)), cell('G2', box(5,0,15,10))], box(0,0,10,10))
        self.assertEqual(result['placementOverlaps'], [{'left': 'G1', 'right': 'G2', 'areaM2': 50}])
        self.assertEqual(result['placementAreaSumM2'], 200)
        self.assertEqual(result['placementAreaUnionM2'], 150)
        self.assertEqual(result['cells'][1]['outsideStudyAreaM2'], 50)

    def test_invalid_fields_and_dimensions_fail(self):
        bad_values = [{'L3_CODE': 154}, {'L3_CODE': 'xx'}, {'L3_NAME': '\ufffd'},
                      {'IMG_DATE': '2023-02-30'}, {'IMG_DATE': '20231231'}]
        for props in bad_values:
            f = feature(box(0,0,10,10))
            f['properties'].update(props)
            with self.subTest(props=props), self.assertRaises(cell_audit.audit.SpatialDataError):
                cell_audit.CoverageIndex([f])
        with self.assertRaises(cell_audit.audit.SpatialDataError):
            cell_audit.CoverageIndex([feature(Polygon([(0,0,0),(1,0,0),(1,1,0)]))])

    def test_building_intersection_unions_duplicates_and_keeps_holes(self):
        a = Polygon(box(127.053,37.543,127.054,37.544).exterior.coords,
                    [box(127.0532,37.5432,127.0538,37.5438).exterior.coords])
        b = box(127.0535,37.543,127.0545,37.544)
        snapshot = {'buildings': [{'id': str(i), 'polygons': [mapping(g)['coordinates']]} for i,g in enumerate([a,b])]}
        boundary = shapely.transform(box(127.052,37.542,127.055,37.545), self.transformer.transform, interleaved=False)
        projected = [shapely.transform(g, self.transformer.transform, interleaved=False) for g in [a,b]]
        report = cell_audit.compare_buildings([cell('G1', boundary)], snapshot, self.transformer)['G1']
        self.assertAlmostEqual(report['unionAreaM2'], projected[0].union(projected[1]).area)
        self.assertLess(report['unionAreaM2'], sum(g.area for g in projected))
        self.assertEqual(report['buildingFeatureCount'], 2)

    def test_private_output_refuses_overwrite_and_escape_and_uses_private_mode(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(cell_audit.audit, 'ROOT', Path(directory).resolve()):
            target = Path(directory).resolve()/'data/private/cell/report.json'
            cell_audit.write_private(target, {'test': 1})
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
            with self.assertRaises(FileExistsError):
                cell_audit.write_private(target, {'test': 2})
            with self.assertRaises(cell_audit.audit.SpatialDataError):
                cell_audit.write_private(Path(directory)/'outside.json', {})
            link = Path(directory).resolve()/'data/private/link'
            link.symlink_to(target.parent, target_is_directory=True)
            with self.assertRaises(cell_audit.audit.SpatialDataError):
                cell_audit.write_private(link/'unsafe.json', {})

    def test_public_summary_removes_geometry_and_binds_full_report(self):
        report = cell_audit.diagnose([feature(box(0,0,10,10))], [cell('G1', box(0,0,10,10))], box(0,0,10,10))
        report.update(inputHashes={'model': 'a'*64}, source={'sha256': 'b'*64}, codeHashes={}, versions={},
                      buildingComparison={'G1': {'buildingFeatureCount': 1, 'unionAreaM2': 20,
                                                 'coveredFraction': .2, 'buildingIds': ['private-link']}})
        public = cell_audit.public_summary(report)
        encoded = cell_audit.report_bytes(public)
        for forbidden in [b'coordinates', b'geometry', b'propertiesSha256', b'buildingIds', b'private-link']:
            self.assertNotIn(forbidden, encoded)
        self.assertEqual(public['reportSha256'], hashlib.sha256(cell_audit.report_bytes(report)).hexdigest())
        self.assertEqual(public['cells'][0]['methods']['linework']['classes'][0]['names'], ['도로'])
