"""원 차로 수와 철도 선형의 표시용 운행 자료 생성."""
import argparse
from collections import defaultdict
from contextlib import closing
import gzip
import json
from pathlib import Path
import sqlite3
import shapely
from shapely.geometry import MultiLineString, Point, LineString
from prepare_topography_objects import object_key
from topography_catalog import SpatialCatalog
from shapely.ops import linemerge
from shapely.strtree import STRtree
import prepare_seoul_topography as source
import prepare_seoul_spatial as spatial
from prepare_native_bridges import BASE, PUBLIC, parts, relative


def build(output):
    if output.exists() or output.is_symlink():
        raise ValueError('기존 교통 자료 덮어쓰기 금지')
    lanes=[]
    with closing(sqlite3.connect('file:'+str(BASE/'objects-v1/objects.sqlite')+'?mode=ro',uri=True)) as db:
        for key,props in db.execute("SELECT o.object_id,a.properties FROM objects o JOIN attribute_variants a ON o.object_id=a.object_id WHERE role='ROAD_CENTERLINE' AND attribute_status='CONSISTENT' ORDER BY o.object_id"):
            value=json.loads(props).get('차로수')
            if str(value).isdigit() and 2<=int(value)<=32:
                w = json.loads(props).get('도로폭')
                try: width = float(w)
                except (TypeError, ValueError): width = 0
                lanes.append([key,int(value),width if 0 < width <= 200 else None])
    networks=defaultdict(dict)
    with closing(sqlite3.connect('file:'+str(BASE/'spatial-v1/spatial.sqlite')+'?mode=ro',uri=True)) as db:
        for fid,wkb,props in db.execute("SELECT fid,geometry_wkb,properties FROM features WHERE layer='N1L_A0150000' AND geometry_status='VALID' AND deleted=0 ORDER BY fid"):
            attrs=json.loads(props);kind=attrs.get('구분');name=attrs.get('명칭') or ''
            if kind not in ('지하철(지상)','보통철도'):continue
            for line in parts(shapely.from_wkb(wkb),'LineString'):
                key=shapely.to_wkb(shapely.normalize(line))
                item=networks[(kind,name)].setdefault(key,dict(geometry=line,fids=[]))
                item['fids'].append(fid)
    routes=[]
    for (kind,name),objects in sorted(networks.items()):
        entries=list(objects.values());lines=[v['geometry'] for v in entries];tree=STRtree(lines)
        # 끝점이 일치하는 선만 연결하며 평면 교차점에 새 분기나 선로를 만들지 않는다.
        merged=linemerge(MultiLineString(lines))
        for line in parts(merged,'LineString'):
            if line.length<45:continue
            fids=sorted({fid for i in tree.query(line) if line.intersection(lines[int(i)]).length>.01 for fid in entries[int(i)]['fids']})
            coords=relative(line)
            routes.append(dict(id=source.digest(shapely.to_wkb(shapely.normalize(line))),kind='subway' if kind=='지하철(지상)' else 'rail',name=name,coordinates=coords,sourceFids=fids))
    routes.sort(key=lambda r:r['id'])
    catalog = SpatialCatalog(BASE/'spatial-v1', json.loads((BASE/'spatial-v1/summary.json').read_bytes()))
    tunnels = []
    seen = set()
    with closing(sqlite3.connect('file:'+str(BASE/'spatial-v1/spatial.sqlite')+'?mode=ro',uri=True)) as db:
        for fid,wkb,props in db.execute("SELECT fid,geometry_wkb,properties FROM features WHERE layer='N1A_A0110020' AND geometry_status='VALID' AND deleted=0 ORDER BY fid"):
            geometry=shapely.from_wkb(wkb);key=object_key('N1A_A0110020',geometry)
            if key in seen: continue
            seen.add(key);attrs=json.loads(props)
            profiles=[]
            for row in catalog.query(geometry.bounds,['N1L_A0020000']):
                for line in parts(row['geometry'].intersection(geometry),'LineString'):
                    if line.length>3:
                        profiles.append(dict(roadId=object_key('N1L_A0020000',row['geometry']),coordinates=relative(line)))
            if profiles:
                original_profiles=profiles
                merged=linemerge(MultiLineString(list({tuple(map(tuple,p['coordinates'])) for p in profiles})))
                profiles=[]
                for line in parts(merged,'LineString'):
                    ids={p['roadId'] for p in original_profiles if line.intersection(LineString(p['coordinates'])).length>.01}
                    profiles.extend(dict(roadId=rid,coordinates=list(line.coords)) for rid in sorted(ids))
            try: clearance=float(attrs.get('높이') or 0)
            except (TypeError,ValueError): clearance=0
            tunnels.append(dict(id=key,sourceFid=fid,name=attrs.get('명칭') or '',polygons=[relative(p) for p in parts(geometry,'Polygon')],profiles=profiles,clearanceM=clearance if 1<clearance<20 else None))
    body=dict(schemaVersion=1,lanes=lanes,routes=routes,tunnels=tunnels)
    raw=(source.canonical(body)+'\n').encode();stored=gzip.compress(raw,compresslevel=6,mtime=0)
    output.mkdir();(output/'transport.json.gz').write_bytes(stored)
    index=dict(schemaVersion=1,id='SEOUL_NGII_TRANSPORT_V1',file='transport.json.gz',sha256=source.digest(raw),bytes=len(raw),storedSha256=source.digest(stored),storedBytes=len(stored),generatorSha256=spatial.file_sha256(__file__),sourceSpatialSha256=json.loads((BASE/'spatial-v1/summary.json').read_bytes())['spatialSha256'],sourceCitySha256=spatial.file_sha256(PUBLIC/'seoul-native-v1/city.json'),counts=dict(lanes=len(lanes),routes=len(routes),tunnels=len(tunnels)),policy=dict(displayOnly=True,observedPositions=False,observedTimetable=False,connections='EXACT_SOURCE_ENDPOINTS',laneWidthM=3.25,railSpeedMps=12,subwaySpeedMps=10,carLengthM=18,maximumCarriages=4,hydraulicInputsChanged=False))
    (output/'index.json').write_text(source.canonical(index)+'\n')
    print(source.canonical(dict(indexSha256=spatial.file_sha256(output/'index.json'),**index['counts'],bytes=len(raw))))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);build(parser.parse_args().output.absolute())
