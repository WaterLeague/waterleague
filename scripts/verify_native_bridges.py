"""공개 교량 파생본의 원형 대응·접속 범위·도로면 포함 대조."""
import argparse
from contextlib import closing
import gzip
import json
from pathlib import Path
import sqlite3
import shapely
from shapely.affinity import translate
from shapely.geometry import shape,LineString,Point,box
import prepare_seoul_topography as source
import prepare_seoul_spatial as spatial
from prepare_topography_scene import ORIGIN
from prepare_topography_objects import object_key
from topography_catalog import SpatialCatalog
BASE=source.ROOT/'data/private/vworld-seoul-topography-20260307'
PUBLIC=source.ROOT/'frontend/public/data/seoul-bridges-v1'
def verify(report):
    index=json.loads((PUBLIC/'index.json').read_bytes());packed=(PUBLIC/index['file']).read_bytes()
    assert source.digest(packed)==index['storedSha256']
    raw=gzip.decompress(packed);assert len(raw)==index['bytes'] and source.digest(raw)==index['sha256']
    catalog=SpatialCatalog(BASE/'spatial-v1',json.loads((BASE/'spatial-v1/summary.json').read_bytes()))
    assert spatial.file_sha256(source.ROOT/'scripts/prepare_native_bridge_levels.py')==index['levelSupplement']['generatorSha256']
    assert spatial.file_sha256(source.ROOT/'scripts/prepare_native_bridge_ownership.py')==index['levelSupplement']['ownershipGeneratorSha256']
    body=json.loads(raw);seen=set();profiles=0;cache={};stair_profiles=0;rail_profiles=0;max_error=0;lower_decks=0;bound_records={}
    city=json.loads((source.ROOT/'frontend/public/data/seoul-native-v1/city.json').read_bytes())
    assert body['waterPolygons']==[p for surface in city['surfaces'] if surface['kind']=='water' for p in surface['polygons']]
    with closing(sqlite3.connect('file:'+str(catalog.database)+'?mode=ro&immutable=1',uri=True)) as db:
        stair_geometries=[shapely.from_wkb(db.execute("SELECT geometry_wkb FROM features WHERE fid=? AND layer='N1A_C0390000' AND geometry_status='VALID'",(fid,)).fetchone()[0]) for fid in index['stairFids']]
        stair_union=translate(shapely.union_all(stair_geometries),-ORIGIN[0],-ORIGIN[1])
        def check_fids(fids, identifiers):
            assert fids
            for fid in fids:
                if fid not in bound_records:
                    layer,wkb=db.execute("SELECT layer,geometry_wkb FROM features WHERE fid=? AND deleted=0 AND geometry_status='VALID'",(fid,)).fetchone()
                    bound_records[fid]=object_key(layer,shapely.from_wkb(wkb))
                assert bound_records[fid] in identifiers
        for group in body['groups']:
            original=[];names=set();kinds=set()
            for fid,identifier in zip(group['sourceFids'],group['sourceIds'],strict=True):
                layer,wkb,properties=db.execute('SELECT layer,geometry_wkb,properties FROM features WHERE fid=?',(fid,)).fetchone()
                attributes=json.loads(properties)
                for field,values in [('명칭',names),('종류',kinds)]:
                    value=attributes.get(field) or (attributes.get('구분') if field=='종류' else None)
                    if isinstance(value,str) and value.strip():values.add(value.strip())
                geometry=shapely.from_wkb(wkb);assert object_key(layer,geometry)==identifier and identifier not in seen
                seen.add(identifier);original.append(geometry)
            assert len(names)<=1 and len({'도로교' if k=='고가차도' else k for k in kinds})<=1
            assert group['names']==sorted(names) and group['kinds']==sorted(kinds)
            union=shapely.union_all(original)
            displayed=shapely.union_all([shape({'type':'Polygon','coordinates':p}) for p in group['polygons']])
            expected=translate(union,-ORIGIN[0],-ORIGIN[1]);assert displayed.symmetric_difference(expected).area<1e-7
            outline=shapely.union_all([shape({'type':'Polygon','coordinates':p}) for p in group['outlinePolygons']])
            assert outline.symmetric_difference(expected).area<1e-7
            owned=shapely.union_all([outline]+[shape({'type':'Polygon','coordinates':p}) for profile in group['profiles'] for p in profile['polygons']]+[shape({'type':'Polygon','coordinates':p}) for s in group.get('sidewalks',[]) for a in s.get('approaches',[]) for p in a['polygons']])
            preserved=shapely.union_all([shape({'type':'Polygon','coordinates':p}) for p in group.get('preservedUnderpassPolygons',[])])
            for cut in group.get('surfaceCuts',[]):
                mask=shapely.union_all([shape({'type':'Polygon','coordinates':p}) for p in cut['polygons']])
                # 공통 경계의 부동소수점 위상 오류를 원 출력 정밀도(1μm)에서 재검사한다.
                assert mask.difference(owned.buffer(.000002)).area<1e-6
                if 'ROAD_AREA' in cut['roles']:assert mask.intersection(preserved).area<1e-6
            for cut in group.get('sourceSurfaceCuts', []):
                mask=shapely.union_all([shape({'type':'Polygon','coordinates':p}) for p in cut['polygons']])
                assert mask.difference(owned.buffer(.000002)).area < 1e-6
                for fid in cut['sourceFids']:
                    layer,wkb=db.execute('SELECT layer,geometry_wkb FROM features WHERE fid=? AND deleted=0 AND geometry_status=\'VALID\'',(fid,)).fetchone()
                    assert layer in ('N1A_A0010000','N1A_A0053326')
                    source_shape=translate(shapely.from_wkb(wkb),-ORIGIN[0],-ORIGIN[1])
                    assert mask.difference(source_shape.buffer(.000002)).area < 1e-6
            if group.get('attachmentPolygons'):
                attachments=shapely.union_all([shape({'type':'Polygon','coordinates':p}) for p in group['attachmentPolygons']])
                supports=shapely.union_all([outline]+[shape({'type':'Polygon','coordinates':p}) for profile in group['profiles'] for p in profile['polygons']]+[shape({'type':'Polygon','coordinates':p}) for s in group.get('sidewalks',[]) for p in s['polygons']]+[shape({'type':'Polygon','coordinates':p}) for s in group.get('sidewalks',[]) for a in s.get('approaches',[]) for p in a['polygons']])
                # 절단된 마이터 모서리의 최대 반경은 hypot(0.3*5,0.3)이며 실제 높이 귀속 거리는 0.3m로 별도 제한한다.
                assert attachments.difference(supports.buffer(1.531,quad_segs=64)).area < 1e-6
                assert supports.difference(attachments.buffer(.000002)).area < 1e-6
            if '지하차도' in group['kinds']:assert not group.get('surfaceCuts')
            for coordinates in group.get('walkPaths',[]):
                assert LineString(coordinates).difference(displayed).length<1e-7
            for sidewalk in group.get('sidewalks',[]):
                check_fids(sidewalk['sourceFids'],{sidewalk['sourceId']})
                surface=shapely.union_all([shape({'type':'Polygon','coordinates':p}) for p in sidewalk['polygons']])
                assert surface.difference(displayed).area<1e-7
                for coordinates in sidewalk['paths']:assert LineString(coordinates).difference(surface).length<1e-7
            lower=group.get('lowerDeck')
            if lower:
                lower_decks+=1
                surface=shapely.union_all([shape({'type':'Polygon','coordinates':p}) for p in lower['polygons']])
                sidewalk=shapely.union_all([shape({'type':'Polygon','coordinates':p}) for p in lower['sidewalks']])
                assert surface.difference(displayed).area<1e-6
                assert sidewalk.difference(surface).area<1e-6
                assert lower['displayOnly'] and lower['geometryBasis']=='SOURCE_AXIS_CLIPPED_TO_SOURCE_BRIDGE'
                for line in lower['walkPaths']:assert LineString(line).difference(sidewalk).length<1e-6
                for line in lower['railPaths']:assert LineString(line).difference(surface).length<1e-6
                allowed=shapely.union_all([shape({'type':'Polygon','coordinates':p}) for profile in group['profiles'] for p in profile['polygons']])
                for approach in lower['approaches']:
                    # 파생 접속면은 1μm 교차 격자에서 생성되므로 같은 출력 정밀도로 비교한다.
                    for p in approach['polygons']:assert shape({'type':'Polygon','coordinates':p}).difference(allowed.buffer(.000002)).area<1e-6
            for profile in group['profiles']:
                if not profile.get('steps'):check_fids(profile['sourceFids'],{r.split(':part:')[0] for r in profile['roadIds']})
                path=LineString(profile['coordinates']);start,end=profile['span'];assert 0<=start<end<=path.length+.01
                if profile.get('islandConnection'):
                    original_lines=[translate(shapely.from_wkb(db.execute('SELECT geometry_wkb FROM features WHERE fid=?',(fid,)).fetchone()[0]),-ORIGIN[0],-ORIGIN[1]) for fid in profile['sourceFids']]
                    assert path.difference(shapely.union_all(original_lines).buffer(.001)).length<1e-6
                    assert start==0 and abs(end-path.length)<1e-6
                polygons=shapely.union_all([shape({'type':'Polygon','coordinates':p}) for p in profile['polygons']])
                if profile.get('steps'):
                    assert not profile['roadIds'] and polygons.difference(stair_union).area<1e-7
                    assert polygons.distance(displayed)<.101
                    stair_profiles+=1;continue
                for along in [start,end]:assert displayed.distance(path.interpolate(along))<(.001 if profile.get('islandConnection') else 1e-6)
                if start>1e-6:assert displayed.boundary.distance(path.interpolate(start))<1e-6
                if end<path.length-1e-6:assert displayed.boundary.distance(path.interpolate(end))<1e-6
                if polygons.is_empty:
                    if profile.get('rail'):rail_profiles+=1
                    else:profiles+=1
                    continue
                bounds=polygons.bounds;areas={}
                for x in range(int(bounds[0]//1000),int(bounds[2]//1000)+1):
                    for y in range(int(bounds[1]//1000),int(bounds[3]//1000)+1):
                        area_layer='N1A_A0160024' if profile.get('rail') else 'N1A_A0010000'
                        key=(x,y,area_layer)
                        if key not in cache:
                            rows=catalog.query((x*1000+ORIGIN[0],y*1000+ORIGIN[1],(x+1)*1000+ORIGIN[0],(y+1)*1000+ORIGIN[1]),[area_layer])
                            cache[key]=[(row['id'],translate(row['geometry'],-ORIGIN[0],-ORIGIN[1])) for row in rows]
                        areas.update(cache[key])
                error=polygons.difference(shapely.union_all(list(areas.values())).buffer(.000002)).area;max_error=max(max_error,error);assert error<1e-6,(group['id'],group['names'],error)
                # 1μm 표시 격자의 경계 반올림과 실제 상판 내부 중복을 구분한다.
                assert polygons.intersection(displayed.buffer(-.000002)).area<1e-6,(group['id'],group['names'],polygons.intersection(displayed).area)
                if profile.get('rail'):rail_profiles+=1
                else:profiles+=1
    from collections import defaultdict
    from prepare_native_bridge_ownership import surface, parts, tangent
    by_road=defaultdict(list); pairs=set(); checked_shared=0
    records=[(g,p) for g in body['groups'] if '지하차도' not in g.get('kinds',[]) for p in g['profiles'] if not p.get('steps') and p['polygons']]
    for i,(g,p) in enumerate(records):
        for rid in p['roadIds']:
            for j in by_road[rid]:
                if (j,i) in pairs:continue
                pairs.add((j,i));other,q=records[j]
                if other is g or bool(p.get('rail')) != bool(q.get('rail')):continue
                shared=surface(p['polygons']).intersection(surface(q['polygons']))
                for piece in parts(shared,'Polygon'):
                    if piece.area<.000001:continue
                    point=piece.representative_point();a=tangent(LineString(p['coordinates']),point);b=tangent(LineString(q['coordinates']),point)
                    if abs(a[0]*b[0]+a[1]*b[1])>.85:
                        assert piece.buffer(-.000002).area<.000001,(g['id'],other['id'],piece.area)
                checked_shared+=1
            by_road[rid].append(i)
    assert len(seen)==index['counts']['sourceObjects'] and profiles+rail_profiles+stair_profiles==index['counts']['profiles']
    assert lower_decks==2
    result=dict(sharedApproachPairsChecked=checked_shared,sharedApproachDuplicateAreaRemovedM2=index['levelSupplement'].get('sharedApproachDuplicateAreaM2',0),derivedBoundaryToleranceM=.000002,landOwnershipGroups=sum(bool(g.get('surfaceCuts')) for g in body['groups']),islandConnections=sum(bool(p.get('islandConnection')) for g in body['groups'] for p in g['profiles']),sourceWaterPolygons=len(body['waterPolygons']),sourceWaterUnchanged=True,lowerDecks=lower_decks,sourceBoundTransportRecords=len(bound_records),schemaVersion=1,status='PASS',indexSha256=spatial.file_sha256(PUBLIC/'index.json'),sourceObjects=len(seen),groups=len(body['groups']),roadProfiles=profiles,railProfiles=rail_profiles,stairProfiles=stair_profiles,
        roleGroups={role:sum(g['role']==role for g in body['groups']) for role in sorted({g['role'] for g in body['groups']})},
        sidewalkSurfaces=sum(len(g.get('sidewalks',[])) for g in body['groups']),pedestrianPaths=sum(len(g.get('walkPaths',[]))+sum(len(s['paths']) for s in g.get('sidewalks',[])) for g in body['groups']),
        distinctSourceNamesAndKindsPreserved=True,displayOutlineUnionUnchanged=True,
        sourcePolygonsUnchanged=True,roadApproachesWithinSourceRoadArea=True,maximumOutsideAreaM2=max_error,displayOnly=True,hydraulicInputsChanged=False)
    report.write_text(source.canonical(result)+'\n');print(source.canonical(result),flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--report',type=Path,required=True);verify(p.parse_args().report)
