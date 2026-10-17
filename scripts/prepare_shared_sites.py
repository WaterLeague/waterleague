"""보관된 공개 도형으로 구 전역 공동 설치 후보 생성. 기존 후보·모델 불변."""
import gzip
import json
import math
from pathlib import Path

from shapely.geometry import Polygon, box
from shapely.strtree import STRtree
from prepare_seoul_play_models import read_shapes, payload, sha, write, PBF_HASH, ORIGIN, ROOT

OUTPUT = ROOT/'backend/src/main/resources/shared-sites'


def main():
    districts, buildings, parkings, source = read_shapes()
    tree = STRtree([b['geometry'] for b in buildings])
    regions = json.loads((ROOT/'data/manifests/seoul-play-v2.json').read_text())['regions']
    catalog = json.loads((ROOT/'data/models/catalog.json').read_text())['models']
    by_hash = {m['sha256']: m for m in catalog}
    entries = []
    for district in districts:
        region = next(r for r in regions if r['districtId'] == district['id'])
        model = json.loads((ROOT/'data/models'/by_hash[region['defaultModelHash']]['file']).read_text())
        legacy = []
        for cell in model['cells']:
            legacy.append(Polygon([(x+region['center'][0]+ORIGIN[0],y+region['center'][1]+ORIGIN[1]) for x,y in cell['coordinates']]))
        legacy_tree = STRtree(legacy)
        cells, shapes = [], []
        boundary = district['geometry']
        def blocked(g):
            return any(g.intersection(legacy[int(i)]).area > .001 for i in legacy_tree.query(g))
        def add(identifier, g, roof, item):
            p = g.representative_point()
            cells.append({'id': identifier, 'kind': 'ROOF' if roof else 'GROUND',
                'name': ('옥상 ' if roof else '주차장 ')+identifier,
                'coordinates': [[round(x-ORIGIN[0],6),round(y-ORIGIN[1],6)] for x,y in g.exterior.coords],
                'center': [round(p.x-ORIGIN[0],6),round(p.y-ORIGIN[1],6)], 'areaM2': g.area,
                'maxAreaM2': math.floor(g.area*(.6 if roof else .8)*100)/100,
                'heightM': item['heightM'] if roof else .12,
                'allowedTypes': ['GREEN_ROOF'] if roof else ['RAIN_GARDEN','PERMEABLE_PAVEMENT'],
                'sourceIds': [item['id']], 'siteEligibility': 'UNKNOWN',
                'areaEvidence': 'OSM_EPSG5186_FOOTPRINT' if roof else 'DESIGN_GRID_INSIDE_OSM_SURFACE_PARKING'})
            shapes.append(g)
        for index in sorted(tree.query(boundary), key=lambda i: buildings[int(i)]['id']):
            item = buildings[int(index)]; g = item['geometry']
            if g.geom_type != 'Polygon' or len(g.interiors) or not 60 <= g.area <= 5000 or not boundary.covers(g) or blocked(g):
                continue
            if item['tags'].get('roof:shape') not in (None, 'flat', 'terrace'):
                continue
            if any(int(other) != int(index) and g.intersection(buildings[int(other)]['geometry']).area > .001 for other in tree.query(g)):
                continue
            add('R'+item['id'][0].upper()+item['id'].split('/')[1],g,True,item)
        ground_seen = set()
        for item in sorted(parkings, key=lambda p:p['id']):
            g = item['geometry']
            if not boundary.covers(g):
                continue
            a,b,c,d=g.bounds
            for x in range(math.ceil(a/10),math.floor(c/10)):
                for y in range(math.ceil(b/10),math.floor(d/10)):
                    identifier=f'G{x}-{y}'
                    if identifier in ground_seen:
                        continue
                    cell=box(x*10,y*10,x*10+10,y*10+10)
                    if g.covers(cell) and not blocked(cell) and len(tree.query(cell,predicate='intersects'))==0:
                        add(identifier,cell,False,item);ground_seen.add(identifier)
        # 생성 순서와 무관하게 식별자 순서로 고정하고 후보의 면적 중첩을 차단한다.
        audit = STRtree(shapes)
        for i,g in enumerate(shapes):
            for j in audit.query(g):
                if int(j)>i and g.intersection(shapes[int(j)]).area>.001:
                    raise ValueError('공동 후보 면적 중첩')
        cells.sort(key=lambda c:c['id'])
        snapshot={'schemaVersion':1,'districtId':district['id'],'sourceSha256':PBF_HASH,
            'baseModelHash':region['defaultModelHash'],'originProjected':ORIGIN,'crs':'EPSG:5186',
            'unitCosts':model['unitCosts'],'budget':model['budget'],
            'eligibility':'UNKNOWN_NOT_CONSTRUCTION_APPROVED','cells':cells}
        raw=payload(snapshot); compressed=gzip.compress(raw,mtime=0)
        filename=district['id']+'-v1.json.gz'
        write(OUTPUT/filename,compressed)
        entry={'districtId':district['id'],'districtName':district['name'],'file':filename,
            'sha256':sha(raw),'gzipSha256':sha(compressed),'bytes':len(raw),
            'count':len(cells),'roofCount':sum(c['kind']=='ROOF' for c in cells),
            'groundCount':sum(c['kind']=='GROUND' for c in cells)}
        entries.append(entry)
        print(district['name'],entry['roofCount'],'옥상',entry['groundCount'],'지상',flush=True)
    manifest={'schemaVersion':1,'sourceSha256':PBF_HASH,
        'extractSha256':source['extractHashes']['seoul-polygons.geojson'],
        'generatorSha256':sha(Path(__file__).read_bytes()),'legacyCount':325,'entries':entries}
    raw=payload(manifest)
    write(OUTPUT/'catalog.json',raw)
    write(ROOT/'data/manifests/shared-sites-v1.json',raw)
    print('catalog',sha(raw),'total',325+sum(e['count'] for e in entries),flush=True)


if __name__=='__main__':
    main()
