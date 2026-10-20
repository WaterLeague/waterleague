"""원 교량·육교 전체와 원 도로로 제한한 표시 접속부 생성."""
import argparse
from collections import defaultdict
from contextlib import closing
import gzip
import json
import math
from pathlib import Path
import sqlite3
import time
import shapely
from shapely.affinity import translate
from shapely.geometry import LineString, Point, box, mapping
from shapely.strtree import STRtree
import prepare_seoul_topography as source
import prepare_seoul_spatial as spatial
from prepare_topography_objects import object_key
from prepare_topography_scene import ORIGIN
from topography_catalog import SpatialCatalog
from prepare_native_street_life import walk_paths
BASE=source.ROOT/'data/private/vworld-seoul-topography-20260307'
PUBLIC=source.ROOT/'frontend/public/data'

def parts(g,kind):
    if g.is_empty:return []
    if g.geom_type==kind:return [g]
    return [p for child in getattr(g,'geoms',[]) for p in parts(child,kind)]
def relative(g):return mapping(translate(g,-ORIGIN[0],-ORIGIN[1]))['coordinates']
def build(output):
    if output.exists() or output.is_symlink():raise ValueError('기존 교량 묶음 덮어쓰기 금지')
    started=time.monotonic()
    summary=json.loads((BASE/'spatial-v1/summary.json').read_bytes())
    catalog=SpatialCatalog(BASE/'spatial-v1',summary)
    bridges=[];seen=set()
    with closing(sqlite3.connect('file:'+str(catalog.database)+'?mode=ro&immutable=1',uri=True)) as db:
        for fid,layer,wkb,properties in db.execute("SELECT fid,layer,geometry_wkb,properties FROM features WHERE layer IN ('N1A_A0070000','N1A_A0063321','N1A_A0090000') AND geometry_status='VALID' AND deleted=0 ORDER BY fid"):
            geometry=shapely.from_wkb(wkb);key=object_key(layer,geometry)
            if key in seen:continue
            attributes=json.loads(properties)
            name=attributes.get('명칭');kind=attributes.get('종류') or attributes.get('구분')
            seen.add(key);bridges.append(dict(id=key,fid=fid,layer=layer,geometry=geometry,
                names={name.strip()} if isinstance(name,str) and name.strip() else set(),
                kinds={kind.strip()} if isinstance(kind,str) and kind.strip() else set()))
    geometries=[b['geometry'] for b in bridges];tree=STRtree(geometries);parents=list(range(len(bridges)))
    names=[set(b['names']) for b in bridges];kinds=[set(b['kinds']) for b in bridges]
    def root(i):
        while parents[i]!=i:parents[i]=parents[parents[i]];i=parents[i]
        return i
    for i,g in enumerate(geometries):
        for j in tree.query(g):
            j=int(j)
            if j<=i or not g.intersects(geometries[j]):continue
            if bridges[i]['layer']!=bridges[j]['layer']:
                pair={bridges[i]['layer'],bridges[j]['layer']}
                if pair!={'N1A_A0070000','N1A_A0090000'} or not bridges[i]['names'] or bridges[i]['names']!=bridges[j]['names']:continue
            a,b=root(i),root(j)
            if a==b:continue
            # 평면 교차·접촉만으로 이름과 용도가 다른 교량을 같은 상판으로 합치지 않는다.
            compatible_kinds={'도로교' if k=='고가차도' else k for k in kinds[a]|kinds[b]}
            if len(names[a]|names[b])>1 or len(compatible_kinds)>1:continue
            parents[b]=a;names[a]|=names[b];kinds[a]|=kinds[b]
    groups=defaultdict(list)
    for i in range(len(bridges)):groups[root(i)].append(bridges[i])
    cache={}
    def nearby(bounds):
        rows={}
        for x in range(math.floor(bounds[0]/1000),math.floor(bounds[2]/1000)+1):
            for y in range(math.floor(bounds[1]/1000),math.floor(bounds[3]/1000)+1):
                key=(x,y)
                if key not in cache:
                    cache[key]=catalog.query((x*1000,y*1000,(x+1)*1000,(y+1)*1000),['N1A_A0010000','N1L_A0020000','N1A_A0160024','N1L_A0150000','N1A_A0033320'])
                for row in cache[key]:rows[row['id']]=row
        return list(rows.values())
    output.mkdir();result=[];profile_count=0;stair_fids=set()
    for members in groups.values():
        union=shapely.union_all([b['geometry'] for b in members]);bounds=union.bounds
        polygon_parts=[p for b in members for p in parts(b['geometry'],'Polygon')]
        profiles=[];sidewalks=[];sidewalk_ids=set()
        rows=nearby((bounds[0]-125,bounds[1]-125,bounds[2]+125,bounds[3]+125))
        for row in rows:
            if row['role']!='SIDEWALK_AREA':continue
            sidewalk_id=object_key('N1A_A0033320',row['geometry'])
            if sidewalk_id in sidewalk_ids:continue
            sidewalk_ids.add(sidewalk_id)
            surface=row['geometry'].intersection(union)
            polygon_surfaces=parts(surface,'Polygon')
            if not polygon_surfaces or surface.area<.1:continue
            sidewalks.append(dict(sourceId=sidewalk_id,
                polygons=[relative(p) for p in polygon_surfaces],
                paths=[relative(p) for p in walk_paths(shapely.union_all(polygon_surfaces))]))
        if members[0]['layer'] in ('N1A_A0070000','N1A_A0090000'):
            rail=any('철교' in b['kinds'] for b in members)
            line_layer='N1L_A0150000' if rail else 'N1L_A0020000'
            area_role='RAILWAY_AREA' if rail else 'ROAD_AREA'
            line_role='RAIL_LINE' if rail else 'ROAD_CENTERLINE'
            rows=nearby((bounds[0]-125,bounds[1]-125,bounds[2]+125,bounds[3]+125))
            roads={};road_props={};areas=[]
            for row in rows:
                g=row['geometry']
                if row['role']==area_role:
                    if g.intersects(union.buffer(125)):areas.append(g)
                elif row['role']==line_role:
                    oid=object_key(line_layer,g)
                    for n,line in enumerate(parts(g,'LineString')):
                        key=oid+':part:'+str(n);roads[key]=line;road_props[key]=row['attributes']
            lines=list(roads.values());ids=list(roads);line_tree=STRtree(lines) if lines else None
            endpoints=defaultdict(list)
            for index,line in enumerate(lines):
                for end,p in enumerate([line.coords[0],line.coords[-1]]):endpoints[(round(p[0],3),round(p[1],3))].append((index,end))
            road_union=shapely.union_all(areas) if areas else None
            used=set()
            for n in ([] if line_tree is None else line_tree.query(union)):
                n=int(n)
                if n in used:continue
                line=lines[n]
                coordinates=list(line.coords);linked={n};prefix=0
                for side in [0,1]:
                    walked=0
                    while walked<max(500,math.hypot(bounds[2]-bounds[0],bounds[3]-bounds[1])+250):
                        p=coordinates[0 if side==0 else -1];q=coordinates[1 if side==0 else -2]
                        # 상판 내부 연결은 끝까지 추적하고 상판 밖 접속 길이만 100m로 제한한다.
                        if Point(p).distance(union)>100:break
                        vx,vy=p[0]-q[0],p[1]-q[1];vl=math.hypot(vx,vy)
                        candidates=[]
                        for other,end in endpoints[(round(p[0],3),round(p[1],3))]:
                            if other in linked:continue
                            other_coords=list(lines[other].coords)
                            if end==1:other_coords.reverse()
                            d=(other_coords[1][0]-p[0],other_coords[1][1]-p[1]);dl=math.hypot(*d)
                            cosine=(vx*d[0]+vy*d[1])/(vl*dl) if vl*dl else -1
                            if cosine>.7:candidates.append((cosine,-other,other,other_coords))
                        if not candidates:break
                        chosen=None
                        for _,_,other,other_coords in sorted(candidates,reverse=True):
                            joined=list(reversed(other_coords[1:]))+coordinates if side==0 else coordinates+other_coords[1:]
                            # 교차로의 순환 선분 때문에 유효한 교량 횡단 경로 전체를 버리지 않는다.
                            if LineString(joined).is_simple:
                                chosen=(other,joined);break
                        if chosen is None:break
                        other,coordinates=chosen;linked.add(other);walked+=lines[other].length
                line=LineString(coordinates)
                if not line.is_simple:continue
                cross=line.intersection(union)
                spans=parts(cross,'LineString')
                if not spans:continue
                span=max(spans,key=lambda p:p.length)
                if span.length<3:continue
                intervals=[line.project(Point(p)) for part in spans for p in [part.coords[0],part.coords[-1]]]
                s0,s1=min(intervals),max(intervals)
                if (s0>1e-6 and union.boundary.distance(line.interpolate(s0))>1e-6) or (s1<line.length-1e-6 and union.boundary.distance(line.interpolate(s1))>1e-6):continue
                center=line.interpolate((s0+s1)/2);near=line.interpolate(min(line.length,(s0+s1)/2+1));before=line.interpolate(max(0,(s0+s1)/2-1))
                dx,dy=near.x-before.x,near.y-before.y;length=math.hypot(dx,dy)
                if length<.1:continue
                normal=(-dy/length,dx/length)
                cross_section=LineString([(center.x-normal[0]*100,center.y-normal[1]*100),(center.x+normal[0]*100,center.y+normal[1]*100)]).intersection(union)
                sections=[p for p in parts(cross_section,'LineString') if p.distance(center)<.01]
                if not sections:continue
                width=max(p.length for p in sections)
                # 2차원 교차만으로 하부 도로를 고가 접속로로 만들지 않는다.
                if span.length<max(4,width*1.8):continue
                path=line
                first=max(0,s0-100);last=min(path.length,s1+100)
                from shapely.ops import substring
                path=substring(path,first,last);s0-=first;s1-=first
                if road_union is None:continue
                approach=path.buffer(min(width/2,40),cap_style='flat',join_style='mitre').intersection(road_union).difference(union)
                polygons=parts(approach,'Polygon')
                if not polygons:continue
                profiles.append(dict(roadIds=sorted(ids[i] for i in linked),coordinates=relative(path),span=[s0,s1],
                    polygons=[relative(p) for p in polygons],displayWidthM=width,rail=rail,
                    lanes=max([int(road_props[ids[i]].get('차로수') or 0) for i in linked if str(road_props[ids[i]].get('차로수') or '').isdigit()]+[0])))
                used.update(linked)
        if members[0]['layer']=='N1A_A0063321':
            stair_rows=catalog.query((bounds[0]-1,bounds[1]-1,bounds[2]+1,bounds[3]+1),['N1A_C0390000'])
            for row in stair_rows:
                stairs=row['geometry']
                if stairs.distance(union)>.1:continue
                for stair in parts(stairs,'Polygon'):
                    rectangle=list(stair.minimum_rotated_rectangle.exterior.coords)
                    a,b=max(zip(rectangle,rectangle[1:]),key=lambda edge:Point(edge[0]).distance(Point(edge[1])))
                    dx,dy=b[0]-a[0],b[1]-a[1];length=math.hypot(dx,dy)
                    if length<1:continue
                    axis=(dx/length,dy/length);center=stair.centroid
                    values=[(p[0]-center.x)*axis[0]+(p[1]-center.y)*axis[1] for p in stair.exterior.coords]
                    first,last=min(values),max(values)
                    ends=[(center.x+axis[0]*t,center.y+axis[1]*t) for t in [first,last]]
                    if Point(ends[0]).distance(union)<Point(ends[1]).distance(union):ends.reverse()
                    path=LineString(ends)
                    profiles.append(dict(roadIds=[],coordinates=relative(path),span=[max(0,path.length-.01),path.length],
                        polygons=[relative(stair)],displayWidthM=stair.area/path.length,steps=True))
                    # 공간 카탈로그 레코드 ID와 원 fid를 다시 대조한다.
                    with closing(sqlite3.connect('file:'+str(catalog.database)+'?mode=ro&immutable=1',uri=True)) as db:
                        match=db.execute("SELECT fid FROM features WHERE layer='N1A_C0390000' AND raw_shape_sha256=? AND geometry_status='VALID'",(row['sourceShapeSha256'],)).fetchall()
                        stair_fids.update(v[0] for v in match)
        record=dict(id=members[0]['id'],role={'N1A_A0070000':'BRIDGE_AREA','N1A_A0063321':'PEDESTRIAN_OVERPASS_AREA','N1A_A0090000':'GRADE_SEPARATED_INTERSECTION_AREA'}['N1A_A0070000' if any(b['layer']=='N1A_A0070000' for b in members) else members[0]['layer']],
            sourceIds=[b['id'] for b in members],sourceFids=[b['fid'] for b in members],
            names=sorted(set().union(*(b['names'] for b in members))),kinds=sorted(set().union(*(b['kinds'] for b in members))),
            polygons=[relative(p) for p in polygon_parts],outlinePolygons=[relative(p) for p in parts(union,'Polygon')],bounds=[bounds[0]-ORIGIN[0],bounds[1]-ORIGIN[1],bounds[2]-ORIGIN[0],bounds[3]-ORIGIN[1]],profiles=profiles,sidewalks=sidewalks,
            walkPaths=[relative(p) for p in walk_paths(union)] if members[0]['layer']=='N1A_A0063321' else [])
        result.append(record);profile_count+=len(profiles)
        if len(result)%100==0:print(source.canonical(dict(groups=len(result),profiles=profile_count,seconds=round(time.monotonic()-started,1))),flush=True)
    body=dict(schemaVersion=1,groups=result)
    raw=(source.canonical(body)+'\n').encode();stored=gzip.compress(raw,compresslevel=6,mtime=0);(output/'structures.json.gz').write_bytes(stored)
    index=dict(schemaVersion=1,id='SEOUL_NGII_BRIDGES_V1',sourceSpatialSha256=summary['spatialSha256'],sourceCitySha256=spatial.file_sha256(PUBLIC/'seoul-native-v1/city.json'),
        generatorSha256=spatial.file_sha256(__file__),file='structures.json.gz',sha256=source.digest(raw),bytes=len(raw),storedSha256=source.digest(stored),storedBytes=len(stored),
        counts=dict(sourceObjects=len(bridges),groups=len(result),profiles=profile_count),stairFids=sorted(stair_fids),policy=dict(displayOnly=True,sourcePolygonsUnchanged=True,grouping='INTERSECTING_COMPATIBLE_SOURCE_NAME_KIND_WITH_NAMED_ROAD_BRIDGE_GRADE_UNION',
            approachClip='SOURCE_TRANSPORT_AREA',connections='SOURCE_ENDPOINTS_ONLY',underpassFilter='SPAN_LENGTH_AT_LEAST_1_8_CROSS_SECTION',
            deckLiftM=6.5,deckThicknessM=.65,maximumApproachM=100,hydraulicInputsChanged=False))
    (output/'index.json').write_text(source.canonical(index)+'\n')
    print(source.canonical(dict(indexSha256=spatial.file_sha256(output/'index.json'),**index['counts'],bytes=len(raw),seconds=round(time.monotonic()-started,1))),flush=True)
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=PUBLIC/'seoul-bridges-v1');build(parser.parse_args().output.absolute())
