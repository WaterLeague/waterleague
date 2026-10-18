"""공개 표면 구성의 원값 보존·면적 배정·명시적 도형 파생 검사."""
from copy import deepcopy
import unittest

from pyproj import CRS
from shapely.geometry import Polygon, box, mapping, shape

from waterleague_sim.engine.flood_errors import FloodModelError
from waterleague_sim.ingestion.seoul_biotope import composition, normalize, soil_cover_parameters
from waterleague_sim.reference.flood_cases import mesh
from waterleague_sim.terrain.composition import assign_composition
from waterleague_sim.terrain.coverage import PolygonLayer
from waterleague_sim.terrain.topology import derive_consensus


def properties(**changes):
    return {'고유번호': 'BLOCK_1', '건폐율': 40., '불투포장율': 30., '투수포장율': 10.,
        '녹지율': 15., '기타비율': 5., '불투토포비': 70., '포장범례': '70%이상~90%미만',
        '토지이용': 'A1', **changes}


def feature(geometry, **changes):
    return {'geometry': mapping(geometry), 'properties': properties(**changes)}


class BiotopeTests(unittest.TestCase):
    def test_permeable_paving_is_separate_and_is_not_native_soil(self):
        value = composition(properties())
        self.assertEqual(value['status'], 'CONSISTENT_REPORTED_COMPOSITION')
        self.assertEqual(value['componentFractions']['permeablePaving'], .1)
        self.assertEqual(value['reportedImperviousFraction'], .7)
        rows, summary = normalize([feature(box(0, 0, 10, 10))], 2025)
        candidates, unresolved = soil_cover_parameters(rows, allocation_evidence='TEST')
        self.assertFalse(candidates)
        self.assertEqual(unresolved[rows[0]['id']], ['PERMEABLE_PAVEMENT_LAYER_PARAMETERS'])
        self.assertEqual(summary['consistentRecords'], 1)

    def test_missing_bad_totals_and_conflicts_preserved_without_normalization(self):
        for changes, issue in [({'녹지율': None}, 'MISSING_OR_NONNUMERIC_PERCENT'),
                               ({'녹지율': True}, 'MISSING_OR_NONNUMERIC_PERCENT'),
                               ({'녹지율': -1.}, 'PERCENT_OUT_OF_RANGE'),
                               ({'녹지율': 16.}, 'COMPONENT_TOTAL_MISMATCH'),
                               ({'불투토포비': 80.}, 'REPORTED_IMPERVIOUS_MISMATCH')]:
            with self.subTest(issue=issue):
                source = properties(**changes)
                value = composition(source)
                self.assertIn(issue, value['issues'])
                self.assertIsNone(value['componentFractions'])
                for key in changes:
                    self.assertEqual(value['raw'][key], source[key])
        self.assertEqual(composition(properties(포장범례='10%미만'))['warnings'],
                         ['LEGEND_DIFFERS_FROM_REPORTED_FRACTION'])

    def test_duplicate_ids_kept_with_row_identity_and_water_not_soil(self):
        rows, summary = normalize([feature(box(0, 0, 5, 10)), feature(box(5, 0, 10, 10),
            건폐율=0., 불투포장율=0., 투수포장율=0., 녹지율=0., 기타비율=100., 불투토포비=0., 토지이용='J1')], 2025)
        self.assertEqual(summary['duplicateOriginalIds'], 1)
        self.assertNotEqual(rows[0]['id'], rows[1]['id'])
        self.assertEqual(rows[0]['properties']['originalId'], rows[1]['properties']['originalId'])
        candidates, unresolved = soil_cover_parameters(rows, allocation_evidence='TEST')
        self.assertFalse(candidates)
        self.assertIn('WATER_BODY_OR_WETLAND_HYDRAULICS', unresolved[rows[1]['id']])
        self.assertIsNone(rows[0]['properties']['validFrom'])

    def test_area_weighted_composition_does_not_renormalize_missing_geometry(self):
        rows, _ = normalize([feature(box(0, 0, 5, 10))], 2025)
        layer = PolygonLayer(rows, lambda x, y: (x, y), {'evidence': 'TEST'})
        result = assign_composition(mesh(1, 1, 10, 10), layer)
        total = result['totals']
        self.assertEqual(total['areaM2'], 100.)
        self.assertEqual(total['knownCompositionAreaM2'], 50.)
        self.assertEqual(total['unresolvedAreaM2'], 50.)
        self.assertEqual(total['componentAreasM2'], {'building': 20., 'imperviousPaving': 15.,
            'permeablePaving': 5., 'vegetation': 7.5, 'bare': 2.5})
        self.assertEqual(total['reportedImperviousAreaM2'], 35.)
        self.assertEqual(total['areaAccountingResidualM2'], 0.)

    def test_invalid_attributes_are_not_implicitly_impervious(self):
        rows, _ = normalize([feature(box(0, 0, 10, 10), 불투토포비=99.)], 2025)
        result = assign_composition(mesh(1, 1, 10, 10),
                                   PolygonLayer(rows, lambda x, y: (x, y), {}))
        self.assertEqual(result['totals']['knownCompositionAreaM2'], 0.)
        self.assertEqual(result['totals']['unresolvedAreaM2'], 100.)
        self.assertEqual(result['totals']['reportedImperviousAreaM2'], 0.)
        self.assertIsNone(result['totals']['knownAreaComponentFractions']['building'])


class TopologyTests(unittest.TestCase):
    def test_agreed_derivation_preserves_original_and_valid_features(self):
        crossed = Polygon([(0, 0), (10, 10), (0, 10), (10, 0), (0, 0)])
        records, _ = normalize([feature(crossed), feature(box(20, 20, 30, 30))], 2025)
        before = deepcopy(records)
        derived, report = derive_consensus(records, CRS.from_epsg(5174).to_wkt())
        self.assertEqual(records, before)
        self.assertEqual(derived[1], records[1])
        self.assertEqual(report['adoptedCount'], 1)
        self.assertEqual(report['unresolvedCount'], 0)
        self.assertTrue(shape(derived[0]['geometry']).is_valid)
        self.assertEqual(shape(derived[0]['geometry']).area, 50.)
        self.assertEqual(report['changedFeatures'][0]['symmetricDifferenceM2'], 0.)
        self.assertEqual((derived, report), derive_consensus(records, CRS.from_epsg(5174).to_wkt()))

    def test_disagreement_and_collapsed_line_remain_unresolved(self):
        holes = Polygon(box(0, 0, 10, 10).exterior.coords,
                        [box(1, 1, 6, 6).exterior.coords, box(4, 4, 9, 9).exterior.coords])
        collapsed = Polygon([(0, 0), (1, 1), (1, 2), (1, 1), (0, 0)])
        rows, _ = normalize([feature(holes), feature(collapsed)], 2025)
        derived, report = derive_consensus(rows, CRS.from_epsg(5174).to_wkt())
        self.assertEqual(derived, rows)
        self.assertEqual(report['unresolvedCount'], 2)
        self.assertEqual(report['changedFeatures'][0]['symmetricDifferenceM2'], 4.)
        with self.assertRaisesRegex(FloodModelError, 'METRIC_SOURCE_REQUIRED'):
            derive_consensus(rows, CRS.from_epsg(4326).to_wkt())


if __name__ == '__main__':
    unittest.main()
