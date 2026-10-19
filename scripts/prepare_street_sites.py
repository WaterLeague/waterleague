"""공개 도로 중심선의 투수포장 설계 구역과 수문 입력을 별도 불변 목록으로 생성."""
import copy
import gzip
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

import pyproj
import shapely
from shapely.affinity import translate
from shapely.geometry import LineString, Polygon, shape
from shapely.strtree import STRtree
from prepare_site_physics import ROOT, DIRECTORY, ORIGIN, Terrain, SOILS, ROUGHNESS, geometry_inputs, sha, encode
from prepare_shared_site_constraints import save
from prepare_seoul_scene_context import tags_of

PRIOR = '2c01768343c093e3afb21fa64c8e298cb79d2cb9371442be7a092ab63c9645de'
SEALED = {'asphalt', 'concrete', 'concrete:plates', 'paving_stones', 'sett', 'paved'}
ROAD = {'primary', 'secondary', 'tertiary', 'residential', 'unclassified', 'living_street', 'service'}
WALK = {'footway', 'pedestrian', 'cycleway'}


def strips(road, tags):
    if road['bridge'] or tags.get('access') in ('no', 'private') or tags.get('surface') not in SEALED | {None}:
        return
    walk = road['class'] in WALK
    if not walk and (road['class'] not in ROAD or not road['motor']):
        return
    roles = [('WALKWAY' if walk else 'ROADWAY', 0., min(1.2 if walk else 2., road['widthM']))]
    if not walk:
        for side, sign in [('left', 1), ('right', -1)]:
            if road['sidewalk'] in (side, 'both', 'yes'):
                roles.append(('SIDEWALK', sign * (road['widthM']/2 + .7), 1.2))
    for segment, (a, b) in enumerate(zip(road['coordinates'], road['coordinates'][1:])):
        dx, dy = b[0]-a[0], b[1]-a[1]
        length = math.hypot(dx, dy)
        if length < 5:
            continue
        for role, offset, width in roles:
            for index in range(math.ceil(length/20)):
                start, end = index*20 + .05, min(length, (index+1)*20) - .05
                if end-start < 5:
                    continue
                points = [(a[0]+dx*s/length-dy*offset/length, a[1]+dy*s/length+dx*offset/length) for s in (start,end)]
                poly = LineString(points).buffer(width/2, cap_style='flat')
                coordinates = [[round(x,6),round(y,6)] for x,y in poly.exterior.coords]
                poly = Polygon(coordinates)
                identity = f"{road['id']}:{role}:{offset}:{segment}:{index}"
                yield identity, role, width, poly


def main():
    prior = (DIRECTORY/'catalog-v9.json').read_bytes()
    if sha(prior) != PRIOR:
        raise ValueError('기존 후보 목록 변경')
    city_raw = (ROOT/'frontend/public/data/seoul-v1/city.json').read_bytes()
    city = json.loads(city_raw)
    districts = [shape({'type':'MultiPolygon','coordinates':d['polygons']}) for d in city['districts']]
    district_tree = STRtree(districts)
    project = pyproj.Transformer.from_crs(4326,5186,always_xy=True,allow_ballpark=False)
    source = json.loads((ROOT/'data/manifests/seoul-city-v1.json').read_bytes())
    raw = (ROOT/'data/private/seoul-city-20261017/seoul-lines.geojson').read_bytes()
    if sha(raw) != source['extractHashes']['seoul-lines.geojson']:
        raise ValueError('도로 원문 변경')
    tags = {f"way/{f['properties']['osm_id']}":tags_of(f['properties']) for f in json.loads(raw)['features']}
    raw = (ROOT/'data/private/seoul-city-20261017/seoul-polygons.geojson').read_bytes()
    if sha(raw) != source['extractHashes']['seoul-polygons.geojson']:
        raise ValueError('제외 도형 원문 변경')
    obstacles = []
    for f in json.loads(raw)['features']:
        t = tags_of(f['properties'])
        if (t.get('building') not in (None,'no') or t.get('natural') == 'water'
                or t.get('waterway') or t.get('landuse') in ('reservoir','basin') or t.get('amenity') == 'parking'):
            g = shape(f['geometry'])
            if not g.is_valid:
                g = shapely.make_valid(g)
            obstacles.append(translate(shapely.transform(g,project.transform,interleaved=False),-ORIGIN[0],-ORIGIN[1]))
    # 기존 후보 전체를 제외해 동일 지표의 중복 설치·점수 합산을 막는다.
    bases = {}
    for e in json.loads(prior)['entries']:
        packed = (DIRECTORY/e['file']).read_bytes(); decoded = gzip.decompress(packed)
        if sha(packed) != e['gzipSha256'] or sha(decoded) != e['sha256']:
            raise ValueError('기존 후보 원문 변경')
        bases[e['districtId']] = (e, json.loads(decoded))
        obstacles.extend(Polygon(c['coordinates']) for c in bases[e['districtId']][1]['cells'])
    obstacles_tree = STRtree(obstacles)
    soil_raw = (ROOT/'data/manifests/seoul-soil-20261018.json').read_bytes()
    soil_geometries, soil_features = [], []
    for page in json.loads(soil_raw)['pages']:
        raw = (ROOT/page['file']).read_bytes()
        if sha(raw) != page['sha256']:
            raise ValueError('토성 원문 변경')
        for f in json.loads(raw)['response']['result']['featureCollection']['features']:
            g = shape(f['geometry'])
            if not g.is_valid or g.is_empty:
                continue
            soil_geometries.append(translate(shapely.transform(g,project.transform,interleaved=False),-ORIGIN[0],-ORIGIN[1]))
            soil_features.append(f)
    soil_tree = STRtree(soil_geometries)
    street_dir = ROOT/'frontend/public/data/seoul-streets-v1'
    street_raw = (street_dir/'catalog.json').read_bytes()
    manifest = json.loads((ROOT/'data/manifests/seoul-streets-v1.json').read_bytes())
    if sha(street_raw) != manifest['catalog']['sha256']:
        raise ValueError('표시 도로 목록 변경')
    roads = {}
    for entry in json.loads(street_raw)['tiles']:
        raw = (street_dir/entry['file']).read_bytes()
        if sha(raw) != entry['sha256']:
            raise ValueError('도로 타일 변경')
        for road in json.loads(raw)['roads']:
            roads[road['id']] = road
    terrain = Terrain(); cells = defaultdict(list); occupied = defaultdict(list); stats = Counter()
    for road in sorted(roads.values(),key=lambda r:r['id']):
        t = tags[road['id'].split(':')[0]]
        for identity, role, width, poly in strips(road,t):
            matches = district_tree.query(poly,predicate='intersects')
            matches = [int(i) for i in matches if districts[int(i)].covers(poly)]
            if len(matches) != 1:
                stats['districtBoundaryExcluded'] += 1; continue
            if any(poly.intersection(obstacles[int(i)]).area > 1e-6 for i in obstacles_tree.query(poly,predicate='intersects')):
                stats['obstacleExcluded'] += 1; continue
            a,b,c,d = poly.bounds
            buckets = [(x,y) for x in range(math.floor(a/25),math.floor(c/25)+1) for y in range(math.floor(b/25),math.floor(d/25)+1)]
            if any(poly.intersection(g).area > 1e-6 for key in buckets for g in occupied[key] if poly.intersects(g)):
                stats['overlapExcluded'] += 1; continue
            district = city['districts'][matches[0]]['id']
            cell = {'id':'S'+sha(identity.encode())[:18], 'kind':'GROUND',
                'name':('차도' if role=='ROADWAY' else '인도' if role=='SIDEWALK' else '보행로')+' · '+str(t.get('name') or '이름 없는 길'),
                'coordinates':list(map(list,poly.exterior.coords)), 'center':[poly.centroid.x,poly.centroid.y],
                'areaM2':poly.area,'maxAreaM2':math.floor(poly.area*100)/100,'heightM':0,
                'allowedTypes':['PERMEABLE_PAVEMENT'],'sourceIds':[road['id'].split(':')[0]],
                'areaEvidence':'PUBLIC_CENTERLINE_DESIGN_STRIP','areaLimitBasis':'PUBLIC_CENTERLINE_DESIGN_STRIP',
                'siteEligibility':'UNKNOWN','eligibilityEvidence':'UNKNOWN_DESIGN_CAP_NOT_SITE_APPROVED','inflowPolicy':'DIRECT_RAINFALL_ONLY'}
            v = geometry_inputs(cell)
            v.update(terrain.sample(cell) or {'slopePercent':1,'slopeMethod':'UNRESOLVED_DESIGN_ASSUMPTION'})
            surface = t.get('surface') if role!='SIDEWALK' else None
            v.update(surfaceTag=surface,imperviousBasis='OSM_SEALED_MATERIAL_CLASSIFICATION' if surface in SEALED else 'SURFACE_UNKNOWN_ASSUMPTION',soilStatus='UNRESOLVED')
            if surface in ROUGHNESS:
                v['nImpervious'] = ROUGHNESS[surface]
            hit = [int(i) for i in soil_tree.query(poly,predicate='intersects') if soil_geometries[int(i)].intersection(poly).area>1e-6]
            if len(hit)==1 and soil_geometries[hit[0]].covers(poly):
                f=soil_features[hit[0]]; label=f['properties']['label']
                if label in SOILS:
                    low,high,suction,texture=SOILS[label]
                    v.update(soilStatus='TEXTURE_CLASS_LITERATURE_ESTIMATE',soilClass=label,soilFeatureId=f['id'],conductivityMmH=low,conductivityRangeMmH=[low,high],suctionMm=suction,textureReference=texture)
            v['streetPlacement']={'streetId':road['id'],'role':role,'widthM':width,'widthBasis':'DESIGN_ASSUMPTION','sourceDate':'2026-10-16','roadWidthBasis':road['widthSource']}
            cell['physicalInputs']=v
            cells[district].append(cell); stats[role]+=1
            for key in buckets:
                occupied[key].append(poly)
    entries=[]
    for district,(entry,base) in bases.items():
        value=copy.deepcopy(base)
        value.update(schemaVersion=10,constraintVersion='PUBLIC_CENTERLINE_PAVEMENT_V10',previousSnapshotSha256=entry['sha256'],cells=cells[district])
        value['physicsEvidence'].update(streetCatalogSha256=sha(street_raw),streetExtractSha256=source['extractHashes']['seoul-lines.geojson'],geometryMethod='PUBLIC_CENTERLINE_DESIGN_STRIP',districtGeometrySha256=sha(city_raw))
        value['limitations'] += ['도로 중심선 기반 차도 폭 2m 이하·인도/보행로 1.2m 이하 설계 구역; 실측 경계·시공 적합성 아님', '2026 도로망을 과거 사건의 대안 설치에 사용; 과거 도로 존재 확인 아님']
        raw=encode(value); packed=gzip.compress(raw,mtime=0); name=f'{district}-v10.json.gz'
        save(DIRECTORY/name,packed)
        entries.append({'districtId':district,'districtName':entry['districtName'],'file':name,'sha256':sha(raw),'gzipSha256':sha(packed),'bytes':len(raw),'count':len(cells[district]),'roofCount':0,'groundCount':len(cells[district])})
        print(district,len(cells[district]),flush=True)
    raw=encode({'schemaVersion':10,'scope':'ADDITIVE_ROAD_AND_WALKWAY_SITES','previousCatalogSha256':PRIOR,'generatorSha256':sha(Path(__file__).read_bytes()),'streetCatalogSha256':sha(street_raw),'soilManifestSha256':sha(soil_raw),'coverage':dict(stats),'entries':entries})
    save(DIRECTORY/'catalog-v10.json',raw); save(ROOT/'data/manifests/shared-sites-v10.json',raw)
    print('catalog',sha(raw),'coverage',dict(stats),flush=True)


if __name__=='__main__':
    main()
