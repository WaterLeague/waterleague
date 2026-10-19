"""OSM 차로·횡단·교량 태그와 연결 높이를 표시 전용 보완 타일로 보존."""
import json,math,heapq,struct
from collections import defaultdict,Counter
from pathlib import Path
import shapely
from shapely.geometry import LineString,Point,Polygon
from shapely.strtree import STRtree
from prepare_seoul_city import ROOT,SOURCE,digest,write
from prepare_seoul_scene_context import tags_of,polygons
OUTPUT=ROOT/'frontend/public/data/street-details-v1'

def main():
    source=json.loads((ROOT/'data/manifests/seoul-city-v1.json').read_bytes())
    raw=(SOURCE/'seoul-lines.geojson').read_bytes()
    if digest(SOURCE/'seoul-lines.geojson')!=source['extractHashes']['seoul-lines.geojson']:raise ValueError('원본 해시 오류')
    tags={f"way/{f['properties']['osm_id']}":tags_of(f['properties']) for f in json.loads(raw)['features']}
    catalog=json.loads((ROOT/'frontend/public/data/seoul-streets-v1/catalog.json').read_bytes())
    roads={}
    for entry in catalog['tiles']:
        for r in json.loads((ROOT/'frontend/public/data/seoul-streets-v1'/entry['file']).read_bytes())['roads']:roads[r['id']]=r
    info=json.loads((ROOT/'frontend/public/data/seoul-terrain-v1/terrain.json').read_bytes())
    raw=(ROOT/'frontend/public/data/seoul-terrain-v1/height-f32le.bin').read_bytes();heights=struct.unpack('<'+'f'*(len(raw)//4),raw)
    def ground(p):
        x=max(0,min(info['width']-1,(p[0]-info['origin'][0])/info['spacing'][0]));y=max(0,min(info['height']-1,(p[1]-info['origin'][1])/info['spacing'][1]));c=int(x);r=int(y);u=x-c;v=y-r
        at=lambda r,c:heights[min(r,info['height']-1)*info['width']+min(c,info['width']-1)]
        return (at(r,c)*(1-u)+at(r,c+1)*u)*(1-v)+(at(r+1,c)*(1-u)+at(r+1,c+1)*u)*v
    values=list(roads.values());lines=[LineString(r['coordinates']) for r in values];tree=STRtree(lines)
    meta={};nodeRoads=defaultdict(list);adj=defaultdict(list)
    for i,(r,line) in enumerate(zip(values,lines)):
        t=tags[r['id'].split(':')[0]];width=r['widthM'];lanes=str(t.get('lanes',''))
        if r['widthSource']=='DISPLAY_ASSUMPTION' and r['motor'] and lanes.isdigit() and 1<=int(lanes)<=12:width=int(lanes)*3.25+.5
        # 실제로 나란한 중심선의 폭만 제한하며 교차로·분기 연결을 잘라내지 않는다.
        if r['motor'] and r['oneway'] and r['widthSource']=='DISPLAY_ASSUMPTION' and line.length>30:
            mid=line.interpolate(.5,normalized=True);a=line.interpolate(.25,normalized=True);b=line.interpolate(.75,normalized=True);dx=b.x-a.x;dy=b.y-a.y
            for j in tree.query(mid.buffer(width),predicate='intersects'):
                q=values[int(j)];other=lines[int(j)]
                if i==j or not q['motor'] or not q['oneway'] or q['bridge']!=r['bridge']:continue
                if t.get('layer','0')!=tags[q['id'].split(':')[0]].get('layer','0'):continue
                d=other.distance(mid)
                if d<2 or d>width:continue
                at=other.project(mid);c=other.interpolate(max(0,at-10));e=other.interpolate(min(other.length,at+10));dot=abs(dx*(e.x-c.x)+dy*(e.y-c.y));den=math.hypot(dx,dy)*c.distance(e)
                if den and dot/den>.985 and 10<at<other.length-10:width=min(width,max(2.5,d-.4))
        footway=t.get('footway','');crossing=t.get('crossing','')
        bridge=r['bridge'] or bool(t.get('bridge:name'))
        layer=max(1,int(t.get('layer','1'))) if bridge and str(t.get('layer','1')).lstrip('-').isdigit() else 0
        m={'id':r['id'],'widthM':round(width,3),'footway':footway,'crossing':crossing,'lanes':int(lanes) if lanes.isdigit() and int(lanes)<=12 else 0,'layer':layer,'bridge':bridge,'bridgeName':t.get('bridge:name', ''),'structure':t.get('bridge:structure',''),'sidewalkLeft':t.get('sidewalk:left',t.get('sidewalk','unknown')),'sidewalkRight':t.get('sidewalk:right',t.get('sidewalk','unknown')),'service':t.get('service','')}
        if m['bridgeName']=='한강대교':m['structure']='arch';m['structureSource']='https://news.seoul.go.kr/culture/archives/508278'
        meta[r['id']]=m
        a,b=tuple(r['coordinates'][0]),tuple(r['coordinates'][-1]);nodeRoads[a].append(i);nodeRoads[b].append(i)
        adj[a].append((b,line.length));adj[b].append((a,line.length))
    print('도로 태그·폭 연결 완료',flush=True)
    # 연결된 교량은 동일 상판 높이를 공유하고 접속 도로에는 완만한 표시 경사를 전달한다.
    nodeZ={};visited=set()
    for i,r in enumerate(values):
        if i in visited or not meta[r['id']]['bridge']:continue
        stack=[i];group=[]
        while stack:
            j=stack.pop()
            if j in visited:continue
            visited.add(j);group.append(j)
            for p in (values[j]['coordinates'][0],values[j]['coordinates'][-1]):
                stack.extend(k for k in nodeRoads[tuple(p)] if k not in visited and meta[values[k]['id']]['bridge'] and meta[values[k]['id']]['layer']==meta[r['id']]['layer'])
        level=max(ground(p) for j in group for p in (values[j]['coordinates'][0],values[j]['coordinates'][-1]))+6.5*max(1,meta[r['id']]['layer'])
        for j in group:
            for p in (values[j]['coordinates'][0],values[j]['coordinates'][-1]):nodeZ[tuple(p)]=max(nodeZ.get(tuple(p),-999),level)
            meta[values[j]['id']]['elevationsM']=[round(level,3)]*len(values[j]['coordinates'])
    heap=[(-z,p) for p,z in nodeZ.items()];heapq.heapify(heap)
    while heap:
        nz,p=heapq.heappop(heap);z=-nz
        if z<nodeZ.get(p,-999)-.001:continue
        for q,length in adj[p]:
            target=z-length*.08
            if target>max(ground(q)+.1,nodeZ.get(q,-999)):
                nodeZ[q]=target;heapq.heappush(heap,(-target,q))
    for r,line in zip(values,lines):
        m=meta[r['id']];a,b=tuple(r['coordinates'][0]),tuple(r['coordinates'][-1]);za=nodeZ.get(a,ground(a));zb=nodeZ.get(b,ground(b))
        if not m['bridge'] and (a in nodeZ or b in nodeZ):
            m['elevationsM']=[round(max(ground(p),za-line.project(Point(p))*.08,zb-(line.length-line.project(Point(p)))*.08),3) for p in r['coordinates']]
        m['junctionStartM']=max([meta[values[j]['id']]['widthM']/2+1 for j in nodeRoads[a] if values[j]['motor'] and values[j]['id']!=r['id']] or [0]) if r['motor'] else 0
        m['junctionEndM']=max([meta[values[j]['id']]['widthM']/2+1 for j in nodeRoads[b] if values[j]['motor'] and values[j]['id']!=r['id']] or [0]) if r['motor'] else 0
    print('교량·접속 높이 연결 완료',flush=True)
    motor=[i for i,r in enumerate(values) if r['motor']];surfaces=[lines[i].buffer(meta[values[i]['id']]['widthM']/2,cap_style='flat',join_style='mitre') for i in motor];motorTree=STRtree(surfaces)
    for i,r in enumerate(values):
        m=meta[r['id']]
        if not r['walk'] or m['footway']=='crossing' or m['bridge']:continue
        area=lines[i].buffer(m['widthM']/2,cap_style='flat',join_style='mitre')
        nearby=[surfaces[int(j)] for j in motorTree.query(area,predicate='intersects') if not meta[values[motor[int(j)]]['id']]['bridge']]
        if nearby:
            clipped=area.difference(shapely.union_all(nearby));m['walkPolygons']=polygons(clipped,[0,0])
    entries=[]
    for e in catalog['tiles']+[catalog['overview']]:
        refs=json.loads((ROOT/'frontend/public/data/seoul-streets-v1'/e['file']).read_bytes())['roads'];file=e['file'];ref=write(OUTPUT/file,[meta[r['id']] for r in refs]);entries.append({'file':file,**ref})
    result=write(OUTPUT/'catalog.json',{'schemaVersion':1,'streetCatalogSha256':digest(ROOT/'frontend/public/data/seoul-streets-v1/catalog.json'),'entries':entries,'modelInput':False})
    counts=Counter(m['footway'] for m in meta.values())
    write(ROOT/'data/manifests/street-details-v1.json',{'catalog':result,'sourceSha256':source['extractHashes']['seoul-lines.geojson'],'terrainSha256':digest(ROOT/'frontend/public/data/seoul-terrain-v1/terrain.json'),'generatorSha256':digest(Path(__file__)),'counts':dict(counts),'bridgeCount':sum(m['bridge'] for m in meta.values()),'limitations':['차로당 3.25m·측방0.5m 표시 폭','교량 층 간 6.5m·접속부 최대8% 표시 경사','아치 치수·경간·교각은 도식 표현','실측 교량고·과거 도로망·수문 입력 아님']})
    print(json.dumps({'catalog':result,'counts':dict(counts),'bytes':sum(e['bytes'] for e in entries)}),flush=True)
if __name__=='__main__':main()
