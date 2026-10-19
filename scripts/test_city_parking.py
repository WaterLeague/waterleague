"""주차 표시의 경계·칸·주행 경로 분리 검증."""
import hashlib
import json
import math
import unittest

import shapely
from shapely.geometry import Polygon, LineString, box, shape
from shapely.strtree import STRtree

from prepare_city_parking import ROOT, spaces


class ParkingDisplayTests(unittest.TestCase):
    def test_layout_preserves_holes_and_access(self):
        area = box(0, 0, 80, 70).difference(box(20, 20, 40, 40))
        access = box(0, 45, 80, 51)
        slots = spaces(area, access)
        self.assertGreater(len(slots), 20)
        for slot in slots:
            polygon = Polygon(slot['corners'])
            self.assertTrue(area.covers(polygon))
            self.assertLess(polygon.intersection(access).area, 1e-6)
        self.assertEqual(slots, spaces(area, access))

    def test_public_snapshot_and_route_separation(self):
        raw = (ROOT/'frontend/public/data/city-parking-v1.json').read_bytes()
        manifest = json.loads((ROOT/'data/manifests/city-parking-v1.json').read_text())
        self.assertEqual(hashlib.sha256(raw).hexdigest(), manifest['sha256'])
        data = json.loads(raw)
        self.assertEqual(len(data['lots']), manifest['lots'])
        self.assertFalse(data['modelInput'])
        shapes = []
        surfaces = []
        slot_count = 0
        for lot in data['lots']:
            area = shape({'type':'MultiPolygon','coordinates':lot['polygons']})
            self.assertTrue(area.is_valid)
            surface = shape({'type':'MultiPolygon','coordinates':lot['surfacePolygons']})
            self.assertTrue(surface.is_valid)
            self.assertLess(surface.difference(area).area, .001)
            surfaces.append(surface)
            shapes.append(area)
            slots = []
            for slot in lot['slots']:
                polygon = Polygon(slot['corners'])
                self.assertTrue(area.buffer(.003).covers(polygon))
                self.assertTrue(surface.buffer(.003).covers(polygon))
                for support in lot['supports']:
                    x,y = support['center']
                    self.assertLess(polygon.intersection(box(x-.6,y-.6,x+.6,y+.6)).area, .001)
                self.assertTrue(all(polygon.intersection(other).area < .003 for other in slots))
                slots.append(polygon)
                # 표시 차체 네 꼭짓점이 주차 칸 안에 있는지 실제 회전 각도로 대조한다.
                x,y = slot['center']; angle = slot['angle']
                car = Polygon([(x+math.cos(angle)*a+math.sin(angle)*b,
                                y+math.sin(angle)*a-math.cos(angle)*b)
                               for a,b in [(-.875,-2.05),(.875,-2.05),(.875,2.05),(-.875,2.05)]])
                self.assertTrue(polygon.buffer(.003).covers(car))
                slot_count += 1
        self.assertEqual(slot_count, manifest['slots'])
        tree = STRtree(shapes)
        aisles = 0
        for route in data['routes']:
            if route['reason'] == 'OSM_PARKING_AISLE':
                self.assertEqual(route['parts'], [])
                aisles += 1
            for coordinates in route['parts']:
                line = LineString(coordinates)
                for index in tree.query(line, predicate='intersects'):
                    self.assertLess(line.intersection(shapes[int(index)]).length, .001)
        self.assertGreater(aisles, 0)
        # 지상 도로·보도의 표시 폭과 주차장 포장이 같은 평면을 점유하지 않는다.
        aisle_ids = {r['id'] for r in data['routes'] if r['reason']=='OSM_PARKING_AISLE'}
        roads = {}
        catalog = json.loads((ROOT/'frontend/public/data/seoul-streets-v1/catalog.json').read_text())
        for tile in catalog['tiles']:
            values = json.loads((ROOT/'frontend/public/data/seoul-streets-v1'/tile['file']).read_text())
            roads.update((r['id'],r) for r in values['roads'])
        surface_tree = STRtree(surfaces)
        for road in roads.values():
            if road['bridge']: continue
            sidewalk = 1.4 if road['motor'] and road['sidewalk']!='no' and not road['class'].startswith(('motorway','trunk')) and road['id'] not in aisle_ids else 0
            corridor = LineString(road['coordinates']).buffer(road['widthM']/2+sidewalk,cap_style='square')
            for index in surface_tree.query(corridor,predicate='intersects'):
                self.assertLess(surfaces[int(index)].intersection(corridor).area,.001)
        print(json.dumps({'lots':len(shapes),'slots':slot_count,'parkingAislesExcluded':aisles,
                          'restrictedRoads':len(data['routes'])}))


if __name__ == '__main__':
    unittest.main()
