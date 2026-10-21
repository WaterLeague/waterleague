"""교량 중복 제거와 실제 육상 연결을 구분하는 회귀 검사."""
import unittest
from shapely.geometry import LineString, Polygon, box, mapping
from prepare_native_bridge_ownership import land_connections, surface_ownership, surface, refine_approaches


def polygons(geometry):
    return [mapping(geometry)['coordinates']]


def road(identifier, points, width=4):
    return dict(id=identifier, geometry=LineString(points), attributes={'도로폭': str(width), '차로수': '2'})


class BridgeOwnershipTest(unittest.TestCase):
    def test_upper_source_surface_removed_without_cutting_crossing_lower_object(self):
        from prepare_native_bridge_ownership import source_surface_ownership
        group = dict(polygons=polygons(box(0,-5,100,5)), profiles=[dict(coordinates=[[-10,0],[110,0]],polygons=[])])
        records = [dict(fid=1,layer='N1A_A0010000',geometry=box(0,-5,100,5)),
            dict(fid=2,layer='N1A_A0010000',geometry=box(47,-20,53,20)),
            dict(fid=3,layer='N1A_A0053326',geometry=box(0,3,100,4))]
        self.assertEqual([c['sourceFids'] for c in source_surface_ownership(group,records)],[[1],[3]])

    def test_island_connection_follows_endpoint_graph_past_turn(self):
        group = dict(role='BRIDGE_AREA', kinds=['도로교'], profiles=[],
            polygons=polygons(box(-10, -3, 0, 3)) + polygons(box(20, -3, 30, 3)))
        roads = [road('north', [(0, 0), (3, 2)]), road('turn', [(3, 2), (3, 5), (0, 5)]),
            road('island', [(3, 2), (17, 2)]), road('south', [(17, 2), (20, 0)])]
        area = box(-10, -8, 30, 8)
        self.assertEqual(land_connections(group, roads, area, Polygon()), 1)
        profile = group['profiles'][0]
        self.assertEqual(profile['roadIds'], ['island:part:0', 'north:part:0', 'south:part:0'])
        self.assertEqual(profile['coordinates'], [(0., 0.), (3., 2.), (17., 2.), (20., 0.)])
        self.assertLess(surface(profile['polygons']).difference(area).area, 1e-7)

    def test_no_island_connection_across_water_or_unconnected_endpoints(self):
        for roads, water in [([road('a', [(0, 0), (20, 0)])], box(4, -10, 8, 10)),
                             ([road('a', [(0, 0), (9, 0)]), road('b', [(10, 0), (20, 0)])], Polygon())]:
            group = dict(role='BRIDGE_AREA', kinds=['도로교'], profiles=[],
                polygons=polygons(box(-10, -3, 0, 3)) + polygons(box(20, -3, 30, 3)))
            self.assertEqual(land_connections(group, roads, box(-10, -10, 30, 10), water), 0)

    def test_transverse_road_between_parallel_bridge_sides_stays_below(self):
        group = dict(role='BRIDGE_AREA', kinds=['도로교'], profiles=[],
            polygons=polygons(box(0, 0, 100, 4)) + polygons(box(0, 8, 100, 12)))
        self.assertEqual(land_connections(group, [road('under', [(50, -5), (50, 20)])], box(0, -5, 100, 20), Polygon()), 0)

    def test_upper_road_copy_removed_but_transverse_underpass_preserved(self):
        group = dict(role='BRIDGE_AREA', kinds=['도로교'], polygons=polygons(box(0, -5, 100, 5)),
            profiles=[dict(roadIds=['upper:part:0'], coordinates=[[-10, 0], [110, 0]], polygons=[])])
        area = box(-10, -10, 110, 10)
        roads = [road('upper', [(-10, 0), (110, 0)], 10), road('under', [(50, -10), (50, 10)], 6)]
        cuts = surface_ownership(group, roads, area, Polygon())
        cut = surface(next(c['polygons'] for c in cuts if 'ROAD_AREA' in c['roles']))
        self.assertTrue(cut.contains(LineString([(10, 0), (40, 0)])))
        self.assertEqual(cut.intersection(box(47, -10, 53, 10)).area, 0)
        self.assertGreater(surface(group['preservedUnderpassPolygons']).area, 0)

    def test_rail_and_pedestrian_bridges_do_not_delete_lower_roads(self):
        for role, kind in [('BRIDGE_AREA', '철교'), ('PEDESTRIAN_OVERPASS_AREA', '')]:
            group = dict(role=role, kinds=[kind], polygons=polygons(box(0, 0, 100, 10)), profiles=[])
            cuts = surface_ownership(group, [], Polygon(), Polygon())
            self.assertFalse(any('ROAD_AREA' in cut['roles'] for cut in cuts))

    def test_upper_sidewalk_copy_is_removed_where_lower_road_is_preserved(self):
        group = dict(role='BRIDGE_AREA', kinds=['도로교'], polygons=polygons(box(0, -5, 100, 5)),
            profiles=[dict(roadIds=['upper:part:0'], coordinates=[[-10, 0], [110, 0]], polygons=[])],
            sidewalks=[dict(polygons=polygons(box(0, 3, 100, 5)))])
        roads = [road('upper', [(-10, 0), (110, 0)], 10), road('under', [(50, -10), (50, 10)], 6)]
        cuts = surface_ownership(group, roads, box(-10, -10, 110, 10), Polygon())
        road_cut = surface(next(c['polygons'] for c in cuts if 'ROAD_AREA' in c['roles']))
        walk_cut = surface(next(c['polygons'] for c in cuts if 'SIDEWALK_AREA' in c['roles']))
        self.assertEqual(road_cut.intersection(box(47, -10, 53, 10)).area, 0)
        self.assertEqual(walk_cut.intersection(box(47, 3, 53, 5)).area, 12)
        surface_ownership(group, roads[:1], box(-10, -10, 110, 10), Polygon())
        self.assertNotIn('preservedUnderpassPolygons', group)

    def test_approaches_use_source_width_and_never_cover_neighbor_deck(self):
        group=dict(profiles=[dict(roadIds=['upper:part:0'],coordinates=[[-20,0],[120,0]],span=[20,120],displayWidthM=30,lanes=8,polygons=polygons(box(-20,-15,0,15))+polygons(box(100,-15,120,15)))],sidewalks=[])
        refine_approaches(group,[road('upper',[(-20,0),(120,0)],10)],box(110,-20,130,20))
        shape=surface(group['profiles'][0]['polygons'])
        self.assertEqual(shape.difference(box(-20,-5,110,5)).area,0)
        self.assertEqual(group['profiles'][0]['displayWidthM'],10)

    def test_transverse_lower_sidewalk_is_not_copied_to_upper_deck(self):
        group=dict(profiles=[dict(roadIds=['upper:part:0'],coordinates=[[0,0],[100,0]],span=[0,100],displayWidthM=10,polygons=[])],sidewalks=[dict(polygons=polygons(box(49,-5,51,5)),paths=[[[50,-5],[50,5]]])])
        refine_approaches(group,[road('upper',[(0,0),(100,0)],10)],Polygon())
        self.assertEqual(group['sidewalks'],[])

    def test_underground_class_does_not_own_raised_surface(self):
        self.assertEqual(surface_ownership({'kinds': ['지하차도']}, [], Polygon(), Polygon()), [])


class SharedApproachTests(unittest.TestCase):
    def test_same_source_approach_has_one_owner_and_crossing_stays_separate(self):
        from prepare_native_bridge_ownership import partition_shared_approaches
        def group(key, coords, area):
            return dict(id=key,kinds=['도로교'],profiles=[dict(roadIds=['shared:part:0'],coordinates=coords,span=[0,10],polygons=polygons(area))])
        a=group('a',[[0,0],[20,0]],box(0,-3,20,3))
        b=group('b',[[10,0],[30,0]],box(10,-3,30,3))
        c=group('c',[[15,-10],[15,10]],box(12,-10,18,10))
        self.assertEqual(partition_shared_approaches([a,b,c]),60)
        self.assertEqual(surface(a['profiles'][0]['polygons']).intersection(surface(b['profiles'][0]['polygons'])).area,0)
        self.assertEqual(surface(c['profiles'][0]['polygons']).area,120)


if __name__ == '__main__':
    unittest.main()
