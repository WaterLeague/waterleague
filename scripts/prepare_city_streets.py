"""보관 OSM 중심선의 서울 도로·보행로 표시 타일 생성."""
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

import pyproj
import shapely
from shapely.geometry import shape, box
from shapely.strtree import STRtree

from prepare_seoul_city import ROOT, SOURCE, ORIGIN, PBF_HASH, digest, write
from prepare_seoul_scene_context import tags_of, above_ground, width_of, WIDTHS

OUTPUT = ROOT / 'frontend/public/data/seoul-streets-v1'
MAJOR = {'motorway', 'trunk', 'primary', 'secondary', 'tertiary'}
WALK = {'footway', 'pedestrian', 'path', 'steps', 'cycleway'}
TILE = 2000


def main():
    source = json.loads((ROOT/'data/manifests/seoul-city-v1.json').read_text())
    if digest(SOURCE/'south-korea-261016.osm.pbf') != PBF_HASH:
        raise ValueError('원본 해시 불일치')
    path = SOURCE/'seoul-lines.geojson'
    if digest(path) != source['extractHashes'][path.name]:
        raise ValueError('중심선 원본 해시 불일치')
    city = json.loads((ROOT/'frontend/public/data/seoul-v1/city.json').read_text())
    boundary = shapely.from_geojson(json.dumps({'type':'MultiPolygon','coordinates':city['boundary']}))
    districts = [shapely.from_geojson(json.dumps({'type':'MultiPolygon','coordinates':d['polygons']})) for d in city['districts']]
    tree = STRtree(districts)
    project = pyproj.Transformer.from_crs(4326, 5186, always_xy=True, allow_ballpark=False)
    tiles = defaultdict(list)
    overview = []
    counts = Counter()
    for f in json.loads(path.read_text())['features']:
        tags = tags_of(f['properties'])
        kind = tags.get('highway')
        if kind not in WIDTHS or not above_ground(tags):
            continue
        g = shape(f['geometry'])
        if g.is_empty or not g.is_valid or g.geom_type not in ('LineString','MultiLineString'):
            continue
        g = shapely.transform(g, project.transform, interleaved=False)
        g = shapely.affinity.translate(g, -ORIGIN[0], -ORIGIN[1]).intersection(boundary)
        if g.is_empty:
            continue
        width, evidence = width_of(tags, 'road')
        pieces = [g] if g.geom_type == 'LineString' else list(getattr(g,'geoms',[]))
        for part_index, part in enumerate(pieces):
            if part.geom_type != 'LineString' or part.length < 2:
                continue
            center = part.interpolate(.5, normalized=True)
            matches = tree.query(center, predicate='intersects')
            if len(matches) == 0:
                continue
            oneway = tags.get('oneway', 'yes' if tags.get('junction')=='roundabout' else 'no')
            road = {'id':f"way/{tags['osm_id']}:{part_index}", 'class':kind,
                    'districtId':city['districts'][int(matches[0])]['id'],
                    'widthM':width, 'widthSource':evidence,
                    'walk':kind in WALK,
                    'motor':kind not in WALK and tags.get('motor_vehicle') not in ('no','private') and tags.get('access') != 'private',
                    'oneway':-1 if oneway=='-1' else 1 if oneway in ('yes','1','true') else 0,
                    'sidewalk':tags.get('sidewalk','unknown'),
                    'bridge':tags.get('bridge') not in (None,'','no','false','0'),
                    'coordinates':[[round(x,2),round(y,2)] for x,y in part.coords]}
            counts[kind] += 1
            if kind in MAJOR:
                overview.append(road)
            a,b,c,d = part.bounds
            for x in range(math.floor(a/TILE),math.floor(c/TILE)+1):
                for y in range(math.floor(b/TILE),math.floor(d/TILE)+1):
                    if part.intersects(box(x*TILE,y*TILE,(x+1)*TILE,(y+1)*TILE)):
                        tiles[f'{x}_{y}'].append(road)
    entries = []
    for key, roads in sorted(tiles.items()):
        x,y = map(int,key.split('_'))
        file = f'tiles/{key}.json'
        ref = write(OUTPUT/file, {'schemaVersion':1,'roads':roads})
        entries.append({'id':key,'file':file,'bounds':[x*TILE,y*TILE,(x+1)*TILE,(y+1)*TILE],**ref})
    overview_ref = write(OUTPUT/'overview.json',{'schemaVersion':1,'roads':overview})
    catalog = {'schemaVersion':1,'sourceSha256':PBF_HASH,'sourceDate':'2026-10-16',
               'coordinateSystem':'EPSG:5186','originProjected':ORIGIN,'tileSizeM':TILE,
               'overview':{'file':'overview.json',**overview_ref},'tiles':entries,
               'counts':dict(counts),'modelInput':False}
    ref = write(OUTPUT/'catalog.json',catalog)
    write(ROOT/'data/manifests/seoul-streets-v1.json',{
        'sourcePage':source['sourceUrl'] if 'sourceUrl' in source else 'https://download.geofabrik.de/asia/south-korea.html',
        'sourceSha256':PBF_HASH,'extractSha256':digest(path),'generatorSha256':digest(Path(__file__)),
        'catalog':ref,'counts':dict(counts),'displayWidthAssumptionsM':WIDTHS,
        'limitations':['폭 없는 도로는 분류별 표시 폭','교량 높이·보도 위치·차선 수는 표시 가정','2026 원본이며 과거 도로망 복원 아님']})
    print(json.dumps({'catalog':ref,'roads':sum(counts.values()),'tiles':len(entries),'overview':len(overview)},ensure_ascii=False))


if __name__ == '__main__':
    import shapely.affinity
    main()
