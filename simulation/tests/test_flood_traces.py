import hashlib
import json
from pathlib import Path
import sys
import unittest

from shapely.geometry import Polygon, box
from shapely import union_all

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from prepare_flood_traces import source_date, membership, geometry_payload, VERSION


class FloodTraceTests(unittest.TestCase):
    def test_source_dates_are_parsed_without_guessing_from_titles(self):
        for value in ['20220808', '2022-08-08', '20220808 - 1800']:
            self.assertEqual(source_date(value).isoformat(), '2022-08-08')
        for value in [None, '', '20220230', '2022/08/08']:
            self.assertIsNone(source_date(value))
        self.assertEqual(membership({'F_SAT_YMD': None, 'F_DISA_NM': '2022년 집중호우'},
                                    '2022-08-08', '2022-08-17'), 'START_DATE_UNKNOWN')
        self.assertEqual(membership({'F_SAT_YMD': '20220817'},
                                    '2022-08-08', '2022-08-17'), 'MATCHED')
        self.assertEqual(membership({'F_SAT_YMD': '20220818'},
                                    '2022-08-08', '2022-08-17'), 'OTHER_EVENT')

    def test_triangulation_retains_holes_and_union_does_not_double_count(self):
        source = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)],
                         holes=[[(2, 2), (4, 2), (4, 4), (2, 4)]])
        combined = union_all([source, box(5, 0, 15, 10)])
        content = geometry_payload(combined)
        values = content['triangleVertices']
        triangles = [Polygon(list(zip(values[i:i+6:2], values[i+1:i+6:2])))
                     for i in range(0, len(values), 6)]
        self.assertAlmostEqual(sum(t.area for t in triangles), 146)
        self.assertLess(union_all(triangles).symmetric_difference(combined).area, 1e-8)
        self.assertIn(',-10.0', content['path'])
        self.assertEqual(content['path'].count('M'), 2)

    def test_immutable_tiles_match_catalog_and_generator_manifest(self):
        directory = ROOT / 'backend/src/main/resources/floodtrace' / VERSION
        raw = (directory / 'catalog.json').read_bytes()
        catalog = json.loads(raw)
        manifest = json.loads((ROOT / f'data/manifests/{VERSION}.json').read_bytes())
        self.assertEqual(hashlib.sha256(raw).hexdigest(), manifest['catalogSha256'])
        self.assertEqual(hashlib.sha256((ROOT / 'scripts/prepare_flood_traces.py').read_bytes()).hexdigest(),
                         manifest['generatorSha256'])
        for event in catalog['events']:
            self.assertEqual(event['includedCount'], event['statusCounts']['INCLUDED'])
            self.assertEqual(sum(v for k, v in event['statusCounts'].items()
                                 if k != 'INCLUDED_WITHOUT_END_DATE'), event['recordCount'])
            triangle_area = 0.
            for tile in event['tiles']:
                content = (directory / event['id'] / f"{tile['id']}.json").read_bytes()
                self.assertEqual(len(content), tile['bytes'])
                self.assertEqual(hashlib.sha256(content).hexdigest(), tile['sha256'])
                geometry = json.loads(content)
                self.assertEqual(set(geometry), {'id', 'eventId', 'path', 'triangleVertices'})
                values = geometry['triangleVertices']
                for i in range(0, len(values), 6):
                    x1, y1, x2, y2, x3, y3 = values[i:i+6]
                    triangle_area += abs((x2-x1)*(y3-y1) - (x3-x1)*(y2-y1)) / 2
            self.assertLess(abs(triangle_area - event['unionAreaM2']) / event['unionAreaM2'], 0.00001)


if __name__ == '__main__':
    unittest.main()
