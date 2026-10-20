"""좌표 가정의 원형 보존·독립 도로 거리·결측 경계 검사."""
import copy
import json
from pathlib import Path
import sys
import unittest

from shapely.geometry import LineString

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts'))
from prepare_seocho_georeference import transform_layout, nearest_samples, samples, summarize, LAYOUT, encode, digest


class GeoreferenceTests(unittest.TestCase):
    def test_published_profile_matches_derivation_and_browser_fixture(self):
        from waterleague_sim.watershed_location import PROFILE, HASH
        profile = json.loads(PROFILE.read_bytes())
        original = json.loads(LAYOUT.read_bytes())
        projected, _ = transform_layout(original, 5181)
        self.assertEqual(digest(PROFILE.read_bytes()), HASH)
        self.assertEqual(profile['sourceLayoutSha256'], digest(LAYOUT.read_bytes()))
        for key in ('nodes', 'links', 'catchments'):
            self.assertEqual(profile[key], projected[key])
        fixture = ROOT/'frontend/src/domains/watershed/view/fixtures/seocho-georeference-v1.json'
        self.assertEqual(digest(encode(json.loads(fixture.read_bytes()))), HASH)

    def test_request_location_claim_is_bound_and_optional(self):
        from waterleague_sim.watershed_location import verify, PROFILE, HASH, FIELDS
        from waterleague_sim.engine.flood_errors import FloodModelError
        profile = json.loads(PROFILE.read_bytes())
        reference = {'profileSha256': HASH, **{k: profile[k] for k in FIELDS}}
        self.assertIsNone(verify({}, profile['sourceOriginalSha256']))
        self.assertEqual(verify({'locationReference': reference}, profile['sourceOriginalSha256']), PROFILE.read_bytes())
        for key, value in [('profileSha256', '0'*64), ('sourceCrsVerified', True),
                           ('assumedSourceCrs', 'EPSG:5174')]:
            with self.assertRaises(FloodModelError):
                verify({'locationReference': reference | {key: value}}, profile['sourceOriginalSha256'])

    def test_projected_identity_and_original_unchanged(self):
        original = json.loads(LAYOUT.read_bytes())
        before = copy.deepcopy(original)
        projected, operation = transform_layout(original, 5181)
        self.assertEqual(original, before)
        self.assertEqual(operation['targetCrs'], 'EPSG:5186')
        # 두 중부원점은 타원체·투영이 같고 북방 가산값만 100km 다르다.
        for a, b in zip(original['nodes'], projected['nodes'], strict=True):
            self.assertEqual(a['id'], b['id'])
            self.assertAlmostEqual(a['coordinate'][0], b['coordinate'][0], places=7)
            self.assertAlmostEqual(a['coordinate'][1]+100000, b['coordinate'][1], places=7)
        for kind in ('links', 'catchments'):
            for a, b in zip(original[kind], projected[kind], strict=True):
                self.assertEqual({k: v for k, v in a.items() if k != 'points'},
                                 {k: v for k, v in b.items() if k != 'points'})
                self.assertEqual(len(a['points']), len(b['points']))

    def test_known_independent_distances_ties_and_missing_roads(self):
        roads = [{'id': 'B', 'geometry': LineString([(0, 0), (100, 0)])},
                 {'id': 'A', 'geometry': LineString([(0, 10), (100, 10)])}]
        points = [{'point': [5, 5], 'weightM': 2}, {'point': [5, 12], 'weightM': 8}]
        rows = nearest_samples(points, roads)
        self.assertEqual([r['distanceM'] for r in rows], [5, 2])
        self.assertEqual(rows[0]['roadId'], 'A')
        self.assertEqual(rows[0]['equidistantRoadCount'], 2)
        self.assertEqual(rows, nearest_samples(points, roads[::-1]))
        self.assertEqual(summarize(rows)['lengthWeightedMeanM'], 2.6)
        missing = nearest_samples([{'point': [5, 211], 'weightM': 1}], roads)
        self.assertIsNone(missing[0]['distanceM'])
        self.assertIsNone(summarize(missing)['meanM'])
        self.assertFalse(summarize(nearest_samples(points, []))['complete'])

    def test_short_and_long_links_preserve_weight_and_midpoints(self):
        points = samples({'nodes': [], 'links': [
            {'id': 'A', 'points': [[0, 0], [25, 0]]},
            {'id': 'B', 'points': [[0, 0], [0, 2]]}]})
        self.assertEqual(len(points), 4)
        self.assertAlmostEqual(sum(p['weightM'] for p in points), 27)
        self.assertEqual(points[-1]['point'], [0, 1])
        self.assertTrue(all(0 < p['weightM'] <= 10 for p in points))
        self.assertAlmostEqual(points[0]['point'][0], 25/6)

    def test_unverified_classification_cannot_be_replaced(self):
        layout = json.loads(LAYOUT.read_bytes())
        layout['horizontalCrs'] = 'EPSG:5181'
        with self.assertRaises(ValueError):
            transform_layout(layout, 5181)


if __name__ == '__main__':
    unittest.main()
