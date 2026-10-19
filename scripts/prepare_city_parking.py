"""보관된 지상 주차장 경계에서 정차 표시와 통행 제외 구간 생성."""
import hashlib
import json
import math
from pathlib import Path

import shapely
from shapely.affinity import rotate, translate
from shapely.geometry import LineString, Point, box
from shapely.strtree import STRtree

from prepare_seoul_city import ROOT, SOURCE, ORIGIN, PBF_HASH, digest, write
from prepare_seoul_play_models import read_shapes
from prepare_seoul_scene_context import tags_of, polygons

OUTPUT = ROOT / 'frontend/public/data/city-parking-v1.json'


def spaces(area, blocked):
    rectangle = list(area.minimum_rotated_rectangle.exterior.coords)
    edges = [(a, b) for a, b in zip(rectangle, rectangle[1:])]
    a, b = max(edges, key=lambda e: math.dist(*e))
    angle = math.degrees(math.atan2(b[1]-a[1], b[0]-a[0]))
    local = rotate(area, -angle, origin=(0, 0))
    west, south, east, north = local.bounds
    safe = area.buffer(-.3).difference(blocked)
    result = []
    # 주차 칸·통로 간격은 표시 배치이며 실제 주차선·대수 관측이 아니다.
    for row in range(math.ceil((north-south)/16)):
        for side in (0, 1):
            y = south + .5 + row*16 + side*11
            for column in range(math.floor((east-west)/2.6)):
                x = west + .3 + column*2.6
                cell = rotate(box(x, y, x+2.5, y+5), angle, origin=(0, 0))
                if not safe.covers(cell):
                    continue
                result.append({'center': [round(cell.centroid.x, 3), round(cell.centroid.y, 3)],
                               'angle': math.radians(angle) + (0 if side else math.pi),
                               'corners': [[round(px, 3), round(py, 3)] for px, py in cell.exterior.coords]})
    return result


def line_parts(geometry):
    if geometry.geom_type == 'LineString':
        return [geometry] if geometry.length > .01 else []
    return [part for child in getattr(geometry, 'geoms', []) for part in line_parts(child)]


def main():
    _, buildings, parkings, manifest = read_shapes()
    raw = SOURCE / 'seoul-lines.geojson'
    if digest(raw) != manifest['extractHashes'][raw.name]:
        raise ValueError('도로 원문 해시 불일치')
    tags = {'way/'+f['properties']['osm_id']: tags_of(f['properties'])
            for f in json.loads(raw.read_text())['features']}
    catalog_path = ROOT/'frontend/public/data/seoul-streets-v1/catalog.json'
    street_manifest = json.loads((ROOT/'data/manifests/seoul-streets-v1.json').read_text())
    if digest(catalog_path) != street_manifest['catalog']['sha256']:
        raise ValueError('도로 목록 해시 불일치')
    roads = {}
    for entry in json.loads(catalog_path.read_text())['tiles']:
        path = catalog_path.parent / entry['file']
        if digest(path) != entry['sha256']:
            raise ValueError('도로 타일 해시 불일치')
        roads.update((r['id'], r) for r in json.loads(path.read_text())['roads'])
    road_shapes = [LineString(r['coordinates']) for r in roads.values()]
    road_values = list(roads.values())
    road_tree = STRtree(road_shapes)
    building_shapes = [translate(b['geometry'], -ORIGIN[0], -ORIGIN[1]) for b in buildings]
    building_tree = STRtree(building_shapes)
    lots, lot_shapes = [], []
    covered = []
    for parking in sorted(parkings, key=lambda p: p['id']):
        area = translate(parking['geometry'], -ORIGIN[0], -ORIGIN[1])
        if any(area.intersection(other).area > .01 for other in covered if area.intersects(other)):
            area = area.difference(shapely.union_all([p for p in covered if area.intersects(p)]))
        if area.is_empty or area.area < 15:
            continue
        covered.append(area)
        obstacles = [building_shapes[int(i)].buffer(.4) for i in building_tree.query(area, predicate='intersects')]
        surface_cuts, bridge_roads = [], []
        for i in road_tree.query(area.buffer(42.4), predicate='intersects'):
            road = road_values[int(i)]
            if road['bridge']:
                bridge_roads.append((road, road_shapes[int(i)]))
                continue
            aisle = tags[road['id'].split(':')[0]].get('service') == 'parking_aisle'
            sidewalk = 1.4 if road['motor'] and road['sidewalk'] != 'no' and not road['class'].startswith(('motorway','trunk')) and not aisle else 0
            width = road['widthM']/2 + sidewalk
            corridor = road_shapes[int(i)].buffer(width, cap_style='square')
            surface_cuts.append(corridor)
            obstacles.append(corridor.buffer(.8))
        blocked = shapely.union_all(obstacles)
        supports = []
        # 교각은 높이 구분용 표시이며 실제 위치·구조 제원이 아니다. 지상 통로와 칸은 피한다.
        for road, line in sorted(bridge_roads, key=lambda r:r[0]['id']):
            for at in range(16, int(line.length), 32):
                point = line.interpolate(at)
                footing = point.buffer(1.1)
                if not area.covers(footing) or blocked.intersects(footing):
                    continue
                direction = line.interpolate(min(line.length, at+.5))
                supports.append({'center':[round(point.x,3),round(point.y,3)],
                                 'angle':math.atan2(direction.y-point.y,direction.x-point.x),
                                 'width':road['widthM']})
                blocked = blocked.union(footing)
        surface = area.difference(shapely.union_all(surface_cuts))
        candidates = spaces(area, blocked)
        # 식별자 기반 고정 선택으로 재생 시각·배속 변경에 따른 차량 이동을 막는다.
        for slot in candidates:
            key = parking['id'] + ':' + json.dumps(slot['center'])
            slot['seed'] = int(hashlib.sha256(key.encode()).hexdigest()[:8], 16) / 2**32
        if len(candidates) > 160:
            candidates = [candidates[round(i*(len(candidates)-1)/159)] for i in range(160)]
        lots.append({'id': parking['id'], 'polygons': polygons(area, [0, 0]),
                     'surfacePolygons': polygons(surface, [0, 0]), 'supports': supports,
                     'bounds': list(area.bounds), 'slots': candidates[:160]})
        lot_shapes.append(area)
    display_widths = []
    for road in road_values:
        lanes = str(tags[road['id'].split(':')[0]].get('lanes', ''))
        if road['bridge'] and road['motor'] and road['widthSource']=='DISPLAY_ASSUMPTION' and lanes.isdigit() and 1<=int(lanes)<=8:
            display_widths.append({'id':road['id'],'lanes':int(lanes),'widthM':min(road['widthM'],int(lanes)*3.25+.75)})
    parking_tree = STRtree(lot_shapes)
    routes = []
    for road, line in zip(road_values, road_shapes):
        if not road['motor'] or road['bridge']:
            continue
        if tags[road['id'].split(':')[0]].get('service') == 'parking_aisle':
            routes.append({'id': road['id'], 'reason': 'OSM_PARKING_AISLE', 'parts': []})
            continue
        # 차체·차선의 폭까지 여유를 두어 주차장 경계를 스치며 통과하지 않게 한다.
        margin = min(2.5, road['widthM']*.23) + 2.5
        nearby = [lot_shapes[int(i)] for i in parking_tree.query(line.buffer(margin), predicate='intersects')]
        if not nearby:
            continue
        safe = line.difference(shapely.union_all(nearby).buffer(margin))
        if safe.equals(line):
            continue
        parts = sorted(line_parts(safe), key=lambda p: line.project(p.interpolate(0)))
        routes.append({'id': road['id'], 'reason': 'PUBLIC_PARKING_BOUNDARY',
                       'parts': [[[round(x, 6), round(y, 6)] for x, y in part.coords]
                                 for part in parts if part.length >= 25]})
    value = {'schemaVersion': 1, 'sourceDate': '2026-10-16',
             'sourceSha256': PBF_HASH,
             'streetCatalogSha256': digest(catalog_path), 'modelInput': False,
             'lots': lots, 'routes': routes, 'displayRoadWidths': display_widths}
    ref = write(OUTPUT, value)
    report = {'file': str(OUTPUT.relative_to(ROOT)), **ref, 'generatorSha256': digest(Path(__file__)),
              'polygonExtractSha256': manifest['extractHashes']['seoul-polygons.geojson'],
              'lineExtractSha256': digest(raw), 'streetCatalogSha256': digest(catalog_path),
              'lots': len(lots), 'slots': sum(len(p['slots']) for p in lots), 'restrictedRoads': len(routes),
              'bridgeSupports': sum(len(p['supports']) for p in lots),
              'limitations': ['지상·포장 태그 확인 주차장만 표시', '칸 위치·정차 대수·차량 색은 고정 게임 연출',
                              '실제 주차선·주차 점유율·과거 주차장 복원 아님', '수문 계산·설치 점수 입력에 미사용']}
    write(ROOT/'data/manifests/city-parking-v1.json', report)
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
