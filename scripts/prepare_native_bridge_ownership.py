"""원 교통 선형으로 교량의 육상 중복 면과 섬 접속부를 구분."""
from collections import defaultdict
import heapq
import math

import shapely
from shapely.geometry import LineString, Point, Polygon, mapping
from shapely.ops import substring


def parts(geometry, kind):
    if geometry.is_empty:
        return []
    if geometry.geom_type == kind:
        return [geometry]
    return [p for child in getattr(geometry, 'geoms', []) for p in parts(child, kind)]


def surface(polygons):
    return shapely.union_all([Polygon(p[0], p[1:]) for p in polygons])


def source_surface_ownership(group, records):
    """교차 위치에서도 원 상부 도로·안전지대 객체만 지면에서 제거."""
    outline = surface(group['polygons'])
    profiles = [p for p in group['profiles'] if not p.get('rail') and not p.get('steps')]
    raised = shapely.union_all([outline] + [surface(p['polygons']) for p in profiles])
    paths = [LineString(p['coordinates']) for p in profiles]
    if not paths or '지하차도' in group.get('kinds', []):
        return []
    result = []
    for record in records:
        shape = record['geometry']
        overlap = shape.intersection(raised)
        if overlap.area < .01:
            continue
        ring = list(shape.minimum_rotated_rectangle.exterior.coords)
        edges = sorted([LineString(pair) for pair in zip(ring, ring[1:])], key=lambda p: p.length)
        if edges[-1].length < edges[0].length * 2:
            continue
        point = overlap.representative_point()
        axis = tangent(edges[-1], edges[-1].centroid)
        upper = tangent(min(paths, key=lambda p: p.distance(point)), point)
        if abs(sum(a*b for a,b in zip(axis, upper))) < .85:
            continue
        if record['layer'] == 'N1A_A0010000' and overlap.area < shape.area * .5:
            continue
        result.append(dict(sourceFids=[record['fid']], polygons=polygons(overlap)))
    return result


def polygons(geometry):
    return [mapping(p)['coordinates'] for p in parts(geometry, 'Polygon') if p.area > .01]


def tangent(line, point):
    along = line.project(point)
    a, b = line.interpolate(max(0, along - 1)), line.interpolate(min(line.length, along + 1))
    dx, dy = b.x - a.x, b.y - a.y
    length = math.hypot(dx, dy)
    return (dx / length, dy / length) if length else (0, 0)


def width(record):
    try:
        value = float(record['attributes'].get('도로폭') or 0)
        return value if math.isfinite(value) and 0 < value <= 200 else None
    except (TypeError, ValueError):
        return None


def land_connections(group, roads, road_area, water):
    outline = surface(group['polygons'])
    components = parts(outline, 'Polygon')
    if len(components) < 2 or group['role'] != 'BRIDGE_AREA' or '철교' in group.get('kinds', []):
        return 0
    axes = []
    for component in components:
        ring = list(component.minimum_rotated_rectangle.exterior.coords)
        axis = LineString(max(zip(ring, ring[1:]), key=lambda pair: Point(pair[0]).distance(Point(pair[1]))))
        axes.append(tangent(axis, axis.centroid))
    graph = defaultdict(list)
    ends = {}
    edges = []
    for record in roads:
        for part, source in enumerate(parts(record['geometry'], 'LineString')):
            for line in parts(source.difference(outline), 'LineString'):
                if line.length < .001 or line.length > 300 or line.intersection(water).length > .01:
                    continue
                nodes = [tuple(round(v, 3) for v in p) for p in [line.coords[0], line.coords[-1]]]
                edge = len(edges)
                edges.append((line, record, part))
                for side, node in enumerate(nodes):
                    graph[node].append((nodes[1 - side], edge, side))
                    point = Point(line.coords[0 if side == 0 else -1])
                    direction = tangent(line, point)
                    # 나란한 상판의 옆면을 가로지르는 하부 도로를 섬 접속부로 올리지 않는다.
                    owners = [i for i, polygon in enumerate(components) if polygon.distance(point) < .001
                              and abs(sum(a*b for a,b in zip(direction,axes[i]))) > .65]
                    if owners:
                        ends[node] = owners
    found = {}
    for start in sorted(ends):
        queue = [(0, start, [])]
        visited = set()
        while queue:
            length, node, path = heapq.heappop(queue)
            if node in visited or length > 300:
                continue
            visited.add(node)
            if node != start and node in ends:
                if set(ends[node]).isdisjoint(ends[start]):
                    pair = tuple(sorted((min(ends[node]), min(ends[start]))))
                    if pair not in found or length < found[pair][0]:
                        found[pair] = (length, path)
                continue
            for other, edge, side in graph[node]:
                if other not in visited:
                    heapq.heappush(queue, (length + edges[edge][0].length, other, path + [(edge, side)]))
    added = 0
    claimed = Polygon()
    for _, path in sorted(found.values(), key=lambda p: p[0]):
        coordinates, ids, corridors, widths, lanes = [], set(), [], [], []
        for edge, side in path:
            line, record, part = edges[edge]
            points = list(line.coords)
            if side:
                points.reverse()
            coordinates.extend(points if not coordinates else points[1:])
            ids.add(record['id'] + ':part:' + str(part))
            w = width(record)
            if w:
                widths.append(w)
                corridors.append(line.buffer(w / 2, cap_style='flat', join_style='mitre'))
            try:
                lanes.append(int(record['attributes'].get('차로수') or 0))
            except (TypeError, ValueError):
                pass
        if not widths or len(coordinates) < 2:
            continue
        line = LineString(coordinates)
        if not line.is_simple or line.length < 2:
            continue
        patch = shapely.union_all(corridors).intersection(road_area).difference(outline).difference(water).difference(claimed)
        if patch.area < .1:
            continue
        # 동일 원 도로를 경사 접속부와 섬 연결면이 서로 다른 높이에 중복 생성하지 않는다.
        for profile in group['profiles']:
            profile['polygons'] = polygons(surface(profile['polygons']).difference(patch))
        group['profiles'].append(dict(roadIds=sorted(ids), coordinates=coordinates, span=[0, line.length],
            polygons=polygons(patch), displayWidthM=min(widths), rail=False,
            lanes=min(32, max(lanes, default=0), max(1, int(min(widths) / 2.7))), islandConnection=True))
        claimed = shapely.union_all([claimed, patch])
        added += 1
    return added


def refine_approaches(group, roads, other_bridges):
    """원 도로폭으로 접속면을 제한하고 동일 통행면의 상·하부 중복을 제거."""
    by_id = {r['id']: r for r in roads}
    claimed = Polygon()
    for profile in sorted(group['profiles'], key=lambda p: (not p.get('islandConnection'), -(p['span'][1]-p['span'][0]))):
        if profile.get('rail') or profile.get('steps'):
            continue
        corridors, widths = [], []
        for rid in profile['roadIds']:
            record = by_id.get(rid.split(':part:')[0])
            if record is None:
                continue
            w = width(record)
            if w:
                widths.append(w)
                corridors.append(record['geometry'].buffer(min(w, profile['displayWidthM']) / 2, cap_style='flat', join_style='mitre'))
        shape = surface(profile['polygons'])
        if corridors:
            shape = shape.intersection(shapely.union_all(corridors))
            profile['displayWidthM'] = min(profile['displayWidthM'], max(widths))
            profile['lanes'] = min(profile.get('lanes', 0), max(1, int(profile['displayWidthM'] / 2.7)))
        shape = surface(polygons(shape))
        mask = surface(polygons(shapely.union_all([other_bridges, claimed], grid_size=.000001)))
        shape = shapely.difference(shape, mask, grid_size=.000001)
        profile['polygons'] = polygons(shape)
        claimed = surface(polygons(shapely.union_all([claimed, surface(profile['polygons'])])))
    paths = [LineString(p['coordinates']) for p in group['profiles'] if not p.get('rail') and not p.get('steps')]
    # 교량을 횡단하는 하부 보도는 별개의 원 선형이며 상부 보도로 복제하지 않는다.
    for sidewalk in group.get('sidewalks', []):
        lines = [LineString(p) for p in sidewalk['paths'] if len(p) > 1]
        if not lines or not paths:
            continue
        line = max(lines, key=lambda p: p.length)
        point = line.interpolate(.5, normalized=True)
        upper = min(paths, key=lambda p: p.distance(point))
        a, b = tangent(line, point), tangent(upper, point)
        if abs(a[0]*b[0]+a[1]*b[1]) < .65:
            sidewalk['polygons'] = []
            sidewalk['paths'] = []
    group['sidewalks'] = [s for s in group.get('sidewalks', []) if s['polygons']]


def surface_ownership(group, roads, road_area, water):
    group.pop('preservedUnderpassPolygons', None)
    if '지하차도' in group.get('kinds', []):
        return []
    outline = surface(group['polygons'])
    profiles = [p for p in group['profiles'] if not p.get('steps')]
    road_profiles = [p for p in profiles if not p.get('rail')]
    rail_profiles = [p for p in profiles if p.get('rail')]
    road_bridge = group['role'] != 'PEDESTRIAN_OVERPASS_AREA' and '철교' not in group.get('kinds', [])
    road_mask = shapely.union_all(([outline] if road_bridge else []) + [surface(p['polygons']) for p in road_profiles])
    paths = [LineString(p['coordinates']) for p in road_profiles]
    protected = []
    if not road_mask.is_empty:
        source_ids = {rid.split(':part:')[0] for p in road_profiles for rid in p['roadIds']}
        rectangle = list(outline.minimum_rotated_rectangle.exterior.coords)
        axis = LineString(max(zip(rectangle, rectangle[1:]), key=lambda pair: Point(pair[0]).distance(Point(pair[1]))))
        for record in roads:
            if record['id'] in source_ids:
                continue
            w = width(record)
            if not w:
                continue
            for source in parts(record['geometry'], 'LineString'):
                for segment in parts(source.intersection(road_mask), 'LineString'):
                    if segment.length < 1:
                        continue
                    middle = segment.interpolate(.5, normalized=True)
                    upper = min(paths, key=lambda p: p.distance(middle)) if paths else axis
                    a, b = tangent(segment, middle), tangent(upper, middle)
                    if abs(a[0] * b[0] + a[1] * b[1]) < .65:
                        protected.append(source.buffer(w / 2, cap_style='flat', join_style='mitre').intersection(road_area))
    underpass = shapely.union_all(protected)
    road_mask = road_mask.difference(underpass).difference(water)
    sidewalk = shapely.union_all([surface(s['polygons']) for s in group.get('sidewalks', [])] +
        [surface(a['polygons']) for s in group.get('sidewalks', []) for a in s.get('approaches', [])] +
        ([outline] if group['role'] == 'PEDESTRIAN_OVERPASS_AREA' else []))
    rail = shapely.union_all(([outline] if '철교' in group.get('kinds', []) else []) +
        [surface(p['polygons']) for p in rail_profiles])
    result = []
    for roles, mask in [
        (['ROAD_AREA', 'INTERSECTION_AREA', 'INTERCHANGE_AREA', 'CROSSWALK_AREA', 'TRAFFIC_SAFETY_AREA'], road_mask),
        # 하부 차도 보존 영역에서도 상부에 귀속된 보도의 지면 사본은 제거한다.
        (['SIDEWALK_AREA'], sidewalk.difference(water)),
        (['RAILWAY_AREA'], rail.difference(water)),
    ]:
        shape = polygons(mask)
        if shape:
            result.append(dict(roles=roles, polygons=shape))
    if not underpass.is_empty:
        preserved = polygons(underpass.intersection(outline).difference(water))
        if preserved:
            group['preservedUnderpassPolygons'] = preserved
    return result


def partition_shared_approaches(groups):
    """같은 원 중심선의 겹친 접속면은 하나의 교량 그룹만 그린다."""
    records = [(g, p) for g in groups if '지하차도' not in g.get('kinds', [])
               for p in g['profiles'] if not p.get('steps') and p['polygons']]
    records.sort(key=lambda item: (not item[1].get('islandConnection'),
                                  -(item[1]['span'][1] - item[1]['span'][0]), item[0]['id']))
    by_source = defaultdict(list)
    removed = 0.
    for record_index, (group, profile) in enumerate(records):
        shape = surface(profile['polygons'])
        path = LineString(profile['coordinates'])
        previous = {i for rid in profile['roadIds'] for i in by_source[rid]}
        for i in sorted(previous):
            other_group, other = records[i]
            if other_group is group or bool(other.get('rail')) != bool(profile.get('rail')):
                continue
            shared = shapely.intersection(shape, surface(other['polygons']), grid_size=.000001)
            other_path = LineString(other['coordinates'])
            duplicates = []
            for piece in parts(shared, 'Polygon'):
                if piece.area < .000001:
                    continue
                point = piece.representative_point()
                a, b = tangent(path, point), tangent(other_path, point)
                if abs(a[0]*b[0]+a[1]*b[1]) > .85:
                    duplicates.append(piece)
            if duplicates:
                duplicate = shapely.union_all(duplicates)
                removed += duplicate.area
                shape = surface(polygons(shapely.difference(shape, duplicate, grid_size=.000001)))
        profile['polygons'] = polygons(shape)
        for rid in profile['roadIds']:
            by_source[rid].append(record_index)
    sidewalk_owners = defaultdict(list)
    for group in groups:
        for sidewalk in group.get('sidewalks', []):
            for approach in sidewalk.get('approaches', []):
                shape = surface(approach['polygons'])
                previous = shapely.union_all(sidewalk_owners[sidewalk['sourceId']])
                shape = surface(polygons(shapely.difference(shape, previous, grid_size=.000001)))
                approach['polygons'] = polygons(shape)
                approach['paths'] = [list(line.coords) for path in approach['paths']
                                     for line in parts(LineString(path).intersection(shape), 'LineString')]
                sidewalk_owners[sidewalk['sourceId']].append(shape)
            sidewalk['approaches'] = [a for a in sidewalk.get('approaches', []) if a['polygons']]
    return removed
