import copy
import hashlib
import json
import sys
import unittest
from pathlib import Path

import pyproj
from shapely.geometry import Polygon, box, mapping, shape

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import prepare_topography_candidates as candidate


def record(identifier, geometry):
    return {'id': identifier, 'geometry': geometry, 'attributes': {}}


def records():
    return {kind: [] for kind in candidate.LAYERS}


class TopographyCandidatesTests(unittest.TestCase):
    def test_ground_requires_complete_road_coverage_and_avoids_all_obstacles(self):
        inputs = records()
        inputs['roads'] = [record('road', box(0,0,50,50))]
        inputs['buildings'] = [record('building', box(0,0,20,20))]
        inputs['railways'] = [record('rail', box(20,0,30,50))]
        inputs['bridges'] = [record('bridge', box(0,30,20,50))]
        selected, info = candidate.select_candidates(inputs, box(0,0,50,50))
        self.assertEqual(len(selected), 5)
        for c in selected:
            self.assertEqual(c['kind'], 'GROUND')
            self.assertEqual(c['geometry'].area, 25)
            self.assertTrue(inputs['roads'][0]['geometry'].covers(c['geometry']))
            for kind in ['buildings','railways','bridges']:
                self.assertFalse(c['geometry'].intersects(inputs[kind][0]['geometry']))
        self.assertEqual(info['selectedAreaSumM2'], info['selectedAreaUnionM2'])

    def test_narrow_road_and_no_road_never_produce_extra_land(self):
        inputs = records()
        empty, _ = candidate.select_candidates(inputs, box(0,0,20,20))
        self.assertEqual(empty, [])
        inputs['roads'] = [record('road', box(0,0,7,7))]
        selected, info = candidate.select_candidates(inputs, box(0,0,20,20))
        self.assertEqual(info['groundEligibleCount'], 1)
        self.assertEqual(len(selected), 1)
        self.assertTrue(selected[0]['geometry'].equals(box(0,0,5,5)))

    def test_roof_source_and_exclusions_remain_distinct(self):
        inputs = records()
        inputs['buildings'] = [record('large', box(0,0,20,20)), record('small', box(30,0,35,5)),
            record('outside', box(90,0,110,20)), record('road-overlap', box(40,0,60,20)),
            record('holes', Polygon(box(0,40,20,60).exterior.coords, [box(5,45,10,50).exterior.coords]))]
        inputs['roads'] = [record('road', box(40,0,60,20))]
        selected, info = candidate.select_candidates(inputs, box(0,0,100,100))
        roofs = [c for c in selected if c['kind'] == 'ROOF']
        self.assertEqual(len(roofs), 1)
        self.assertEqual(roofs[0]['id'], 'R1')
        self.assertEqual(roofs[0]['sourceIds'], ['large'])
        self.assertTrue(roofs[0]['geometry'].equals(inputs['buildings'][0]['geometry']))
        self.assertEqual(info['roofExcludedCounts'], {
            'BELOW_ROOF_AREA_THRESHOLD': 1, 'OUTSIDE_STUDY': 1,
            'TRANSPORT_AREA_OVERLAP': 1, 'UNSUPPORTED_HOLES_OR_MULTIPART': 1})

    def test_boundary_contact_rejects_ground_without_exaggerating_roof_overlap(self):
        inputs = records()
        inputs['roads'] = [record('road', box(0,0,5,5))]
        inputs['railways'] = [record('rail', box(5,0,10,5))]
        selected, info = candidate.select_candidates(inputs, box(0,0,20,20))
        self.assertEqual(selected, [])
        self.assertEqual(info['groundEligibleCount'], 0)
        inputs['buildings'] = [record('roof', box(0,5,10,15))]
        selected, _ = candidate.select_candidates(inputs, box(0,0,20,20))
        self.assertEqual([c['kind'] for c in selected], ['ROOF'])

    def test_order_is_deterministic_and_does_not_change_source(self):
        inputs = records()
        inputs['roads'] = [record('road-b', box(0,0,20,40)), record('road-a', box(20,0,40,40))]
        before = copy.deepcopy(inputs)
        selected, info = candidate.select_candidates(inputs, box(0,0,40,40))
        repeated, info_again = candidate.select_candidates({k:list(reversed(v)) for k,v in inputs.items()}, box(0,0,40,40))
        self.assertEqual(selected, repeated)
        self.assertEqual(info, info_again)
        self.assertEqual(inputs, before)
        self.assertEqual(len({c['gridId'] for c in selected}), len(selected))

    def test_invalid_and_overlapping_roof_geometry_cannot_pass(self):
        inputs = records()
        inputs['buildings'] = [record('bad', Polygon([(0,0),(10,10),(0,10),(10,0)]))]
        with self.assertRaises(candidate.audit.SpatialDataError):
            candidate.select_candidates(inputs, box(0,0,30,30))
        inputs['buildings'] = [record('a', box(0,0,20,20)), record('b', box(10,0,30,20))]
        with self.assertRaises(candidate.audit.SpatialDataError):
            candidate.select_candidates(inputs, box(0,0,30,30))

    def test_original_native_display_and_geographic_coordinates_are_bound(self):
        transformer = pyproj.Transformer.from_crs(4326,5186,always_xy=True)
        x,y = transformer.transform(127.054,37.544)
        original = box(x,y,x+5,y+5)
        selected = [{'id': 'G1', 'kind': 'GROUND', 'sourceIds': ['road'],
                     'geometry': original, 'attributes': {}}]
        result = candidate.serialize(selected, transformer, [x,y])[0]
        self.assertEqual(result['areaM2'], 25)
        self.assertEqual(result['siteEligibility'], 'UNKNOWN')
        self.assertTrue(shape(result['nativeGeometry']).equals(original))
        self.assertTrue(Polygon([(dx+x,dy+y) for dx,dy in result['coordinates']]).equals(original))
        for lon,lat in result['geographicGeometry']['coordinates'][0]:
            px,py = transformer.transform(lon,lat)
            self.assertLess(original.boundary.distance(shape({'type':'Point','coordinates':[px,py]})), 1e-7)
        self.assertNotIn('heightM', result)
        self.assertNotIn('slopePercent', result)

    def test_published_candidates_match_source_buildings_and_frozen_generator(self):
        root = candidate.audit.ROOT
        data = json.loads((root/'data/derived/seongsu-topography-candidates-v2.json').read_text())
        source = json.loads((root/'backend/src/main/resources/spatial/seongsu-buildings.json').read_text())
        by_id = {b['id']: b for b in source['buildings']}
        self.assertEqual(data['status'], 'CANDIDATE_SET_NOT_ACTIVE')
        self.assertEqual(data['policy'], candidate.POLICY)
        self.assertEqual(data['generatorSha256'], hashlib.sha256(Path(candidate.__file__).read_bytes()).hexdigest())
        self.assertEqual(data['registrySha256'], candidate.audit.digest(root/'data/manifests/seongsu-topography-sources.json'))
        self.assertEqual(data['auditHelperSha256'], candidate.audit.digest(Path(candidate.audit.__file__)))
        west,south,east,north = data['boundsWgs84']
        for c in data['cells']:
            self.assertEqual(c['siteEligibility'], 'UNKNOWN')
            self.assertAlmostEqual(shape(c['nativeGeometry']).area, c['areaM2'])
            geographic = shape(c['geographicGeometry'])
            self.assertTrue(box(west,south,east,north).covers(geographic))
            if c['kind'] == 'ROOF':
                original = by_id[c['sourceIds'][0]]
                self.assertEqual(len(original['polygons']), 1)
                expected = shape({'type': 'Polygon', 'coordinates': original['polygons'][0]})
                self.assertTrue(geographic.equals_exact(expected, tolerance=1e-10, normalize=True))
