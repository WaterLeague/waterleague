"""주변 표시 도형의 좌표·계보와 지하 선형 제외 검사."""
import hashlib
import json
import sys
import unittest
from pathlib import Path

from shapely.geometry import Polygon, box

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts'))
from prepare_seoul_scene_context import above_ground, width_of


class SceneContextTests(unittest.TestCase):
    def test_all_regions_keep_base_maps_and_valid_local_geometry(self):
        manifest = json.loads((ROOT/'data/manifests/seoul-context-v1.json').read_text())
        registry = json.loads((ROOT/'frontend/public/data/maps.json').read_text())
        by_id = {m['id']: m for m in registry['maps']}
        self.assertFalse(manifest['modelInput'])
        self.assertEqual(manifest['generatorSha256'], hashlib.sha256((ROOT/'scripts/prepare_seoul_scene_context.py').read_bytes()).hexdigest())
        self.assertEqual(len(manifest['maps']), 25)
        scope = box(-500.001, -500.001, 500.001, 500.001)
        holes = 0
        for report in manifest['maps']:
            entry = by_id[report['mapId']]
            raw = (ROOT/'frontend/public/data'/report['file']).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), report['sha256'])
            self.assertEqual(len(raw), report['bytes'])
            self.assertEqual(entry['context']['sha256'], report['sha256'])
            self.assertEqual(entry['sha256'], report['baseMapSha256'])
            base_raw = (ROOT/'frontend/public/data'/entry['file']).read_bytes()
            self.assertEqual(hashlib.sha256(base_raw).hexdigest(), report['baseMapSha256'])
            base, context = json.loads(base_raw), json.loads(raw)
            self.assertEqual(context['originProjected'], base['originProjected'])
            self.assertEqual(context['sourceSha256'], base['sourceHash'])
            self.assertFalse(context['modelInput'])
            self.assertTrue(context['labels'])
            for f in context['features']:
                if f['kind'] in ('road', 'rail'):
                    self.assertTrue(above_ground(f['sourceTags']))
                    self.assertGreater(f['widthM'], 0)
                    self.assertIn(f['widthEvidence'], ('OSM_WIDTH_TAG', 'DISPLAY_ASSUMPTION'))
                for polygon in f['polygons']:
                    g = Polygon(polygon[0], polygon[1:]); holes += len(polygon)-1
                    self.assertTrue(g.is_valid)
                    self.assertTrue(scope.covers(g))
                    self.assertGreater(g.area, 0)
        self.assertGreater(holes, 0)

    def test_unknown_width_and_underground_do_not_become_surveyed_surfaces(self):
        self.assertEqual(width_of({'highway':'residential', 'width':'6.2 m'}, 'road'), (6.2, 'OSM_WIDTH_TAG'))
        for value in ('6-8', '12 ft', 'NaN', '0', '90'):
            self.assertEqual(width_of({'highway':'residential', 'width':value, 'maxwidth':'2'}, 'road'), (7, 'DISPLAY_ASSUMPTION'))
        for tags in ({'tunnel':'yes'}, {'covered':'arcade'}, {'location':'underground'}, {'layer':'-1'}, {'indoor':'yes'}, {'layer':'NaN'}):
            self.assertFalse(above_ground(tags))
        self.assertTrue(above_ground({'tunnel':'no', 'bridge':'yes', 'layer':'1'}))
