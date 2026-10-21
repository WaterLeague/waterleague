"""표시 차로 수·운행 경로의 원 레코드와 해시 대조."""
import argparse
from contextlib import closing
import gzip
import json
from pathlib import Path
import sqlite3
import shapely
from shapely.geometry import LineString
from shapely.affinity import translate
import prepare_seoul_topography as source
import prepare_seoul_spatial as spatial
from prepare_topography_scene import ORIGIN
BASE=source.ROOT/'data/private/vworld-seoul-topography-20260307'
PUBLIC=source.ROOT/'frontend/public/data/seoul-transport-v1'
def verify(report):
 index=json.loads((PUBLIC/'index.json').read_bytes());packed=(PUBLIC/index['file']).read_bytes();raw=gzip.decompress(packed)
 assert source.digest(packed)==index['storedSha256'] and source.digest(raw)==index['sha256'] and len(raw)==index['bytes']
 assert spatial.file_sha256(source.ROOT/'scripts/prepare_native_transport.py')==index['generatorSha256']
 body=json.loads(raw);maximum=0
 with closing(sqlite3.connect('file:'+str(BASE/'objects-v1/objects.sqlite')+'?mode=ro',uri=True)) as objects:
  for oid,count in body['lanes']:
   rows=objects.execute('SELECT a.properties,o.attribute_status FROM attribute_variants a JOIN objects o ON o.object_id=a.object_id WHERE a.object_id=?',(oid,)).fetchall()
   assert len(rows)==1 and rows[0][1]=='CONSISTENT' and int(json.loads(rows[0][0])['차로수'])==count
 with closing(sqlite3.connect('file:'+str(BASE/'spatial-v1/spatial.sqlite')+'?mode=ro',uri=True)) as db:
  cache={}
  for route in body['routes']:
   parts=[]
   for fid in route['sourceFids']:
    if fid not in cache:
     wkb,props=db.execute("SELECT geometry_wkb,properties FROM features WHERE fid=? AND layer='N1L_A0150000' AND deleted=0 AND geometry_status='VALID'",(fid,)).fetchone()
     cache[fid]=(translate(shapely.from_wkb(wkb),-ORIGIN[0],-ORIGIN[1]),json.loads(props))
    line,attrs=cache[fid];parts.append(line)
    assert attrs['구분']==('지하철(지상)' if route['kind']=='subway' else '보통철도')
   path=LineString(route['coordinates']);error=path.difference(shapely.union_all(parts).buffer(.000001)).length
   maximum=max(maximum,error);assert error<.0001
 assert len(body['lanes'])==index['counts']['lanes'] and len(body['routes'])==index['counts']['routes']
 result=dict(status='PASS',**index['counts'],sourceRailRecords=len(cache),maximumOutsideSourceLengthM=maximum,observedPositions=False,observedTimetable=False,indexSha256=spatial.file_sha256(PUBLIC/'index.json'))
 report.write_text(source.canonical(result)+'\n');print(source.canonical(result))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--report',type=Path,required=True);verify(p.parse_args().report)
