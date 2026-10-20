"""누락된 원 주차장 후보를 기존 후보와 겹치지 않게 추가한 계산 카탈로그 생성."""
import argparse,json,shutil,sqlite3,sys
from collections import Counter
from contextlib import closing
from pathlib import Path
import shapely
from shapely.geometry import shape,mapping
import prepare_seoul_topography as source
import prepare_seoul_spatial as spatial
from prepare_topography_objects import object_key,DistrictAssignment,BOUNDARIES
from prepare_topography_sites import candidate_key,ground_geometry,MASK_ROLES
from topography_catalog import SpatialCatalog
BASE=source.ROOT/'data/private/vworld-seoul-topography-20260307'
BASE_SHA='4ec7535e7cbaf41dc73f73519d77ba11f956f4c75c1a574fffa08f16625919b7'
sys.path.insert(0,str(source.ROOT/'simulation'))
from waterleague_sim.spatial import playing_profile,geometry as geometry_code

def build(output):
    if output.exists():raise ValueError('기존 후보 카탈로그 덮어쓰기 금지')
    if spatial.file_sha256(BASE/'play-v1/play.sqlite')!=BASE_SHA:raise ValueError('기존 후보 원본 불일치')
    catalog=SpatialCatalog(BASE/'spatial-v1',json.loads((BASE/'spatial-v1/summary.json').read_bytes()))
    district=DistrictAssignment(json.loads(BOUNDARIES.read_bytes()))
    decisions=[];records=[];seen=set();counts=Counter();numbers=Counter();prior=[]
    with closing(sqlite3.connect('file:'+str(catalog.database)+'?mode=ro&immutable=1',uri=True)) as db, closing(sqlite3.connect('file:'+str(BASE/'play-v1/play.sqlite')+'?mode=ro&immutable=1',uri=True)) as old:
        layers=[r[0] for r in db.execute('SELECT DISTINCT layer FROM layers WHERE scale_denominator=1000 AND role IN ('+','.join('?' for _ in MASK_ROLES)+')',MASK_ROLES)]
        for fid,raw,attrs in db.execute("SELECT fid,geometry_wkb,properties FROM features WHERE layer='N1A_C0430000' AND geometry_status='VALID' AND deleted=0 ORDER BY fid"):
            original=shapely.from_wkb(raw);oid=object_key('N1A_C0430000',original)
            if oid in seen:continue
            seen.add(oid);assigned,_=district.assign(original)
            if assigned is None:counts['outsideDistrict']+=1;continue
            props=json.loads(attrs);a,b,c,d=original.bounds
            masks=[r['geometry'] for r in catalog.query((a,b,c,d),layers)]
            # 이미 운영 중인 후보의 도형·식별자를 유지하고 아직 배분되지 않은 주차면만 추가한다.
            rows=old.execute("SELECT s.id,s.body FROM site_bounds r JOIN sites s ON s.fid=r.fid WHERE r.maxx>=? AND r.minx<=? AND r.maxy>=? AND r.miny<=? AND s.kind='GROUND'",(a,c,b,d))
            previous=[]
            for identifier,body in rows:
                g=shape(json.loads(body)['geometry'])
                if g.intersection(original).area>1e-7:masks.append(g);previous.append(identifier)
            masks.extend(g for g in prior if g.intersects(original))
            candidate=ground_geometry(original,masks)
            if candidate is None or geometry_code.area_limit(candidate)<=0:
                decisions.append(dict(sourceId=oid,sourceFid=fid,status='COVERED_BY_EXCLUSIONS_OR_EXISTING_CANDIDATES',existingCandidateIds=previous));counts['covered']+=1;continue
            assigned,_=district.assign(candidate)
            if assigned is None:counts['outsideDistrict']+=1;continue
            identifier,sha=candidate_key(oid,candidate);center=candidate.representative_point();limit=geometry_code.area_limit(candidate)
            cell=dict(id=identifier,sourceObjectId=oid,sourceIds=[oid],districtId=assigned,kind='GROUND',role='PARKING_AREA',geometry=mapping(candidate),geometryCrs='EPSG:5186',geometrySha256=sha,areaM2=candidate.area,maxAreaM2=float(limit),siteEligibility='UNKNOWN',inflowPolicy='DIRECT_RAINFALL_ONLY')
            cell.update(playing_profile.bind(cell,props))
            if cell['allowedTypes']!=['PERMEABLE_PAVEMENT']:raise ValueError('주차면 비교 시설 결속 실패')
            numbers[assigned]+=1
            cell['displayName']=(props.get('명칭') or '주차장')+' · '+str(numbers[assigned]);cell['address']=None
            records.append(cell);prior.append(candidate);counts['added']+=1
            decisions.append(dict(sourceId=oid,sourceFid=fid,candidateId=identifier,status='ADDED',sourceAreaM2=original.area,areaM2=candidate.area,existingCandidateIds=previous))
    evidence=dict(schemaVersion=1,sourceCatalogSha256=BASE_SHA,sourceSpatialSha256=catalog.summary['spatialSha256'],sourceLayer='N1A_C0430000',counts=dict(counts),decisions=decisions,records=records,policy=dict(existingCandidatesUnchanged=True,priorCandidatesSubtracted=True,sourceFootprintsPreserved=True,constructionEligibility='UNKNOWN',surfaceScenario='PAVEMENT_REFERENCE'))
    output.mkdir(parents=True);evidence_raw=(source.canonical(evidence)+'\n').encode();(output/'parking-extension.json').write_bytes(evidence_raw)
    shutil.copyfile(BASE/'play-v1/play.sqlite',output/'play.sqlite')
    with closing(sqlite3.connect(output/'play.sqlite')) as db:
        for cell in records:
            cell['geometrySources']=dict(sitesSha256=source.digest(evidence_raw),objectsSha256=catalog.summary['spatialSha256'],sourceLayer='N1A_C0430000')
            cursor=db.execute('INSERT INTO sites(id,object_id,district_id,kind,role,status,allowed_mask,cx,cy,body) VALUES(?,?,?,?,?,?,?,?,?,?)',(cell['id'],cell['sourceObjectId'],cell['districtId'],cell['kind'],cell['role'],cell['status'],2,*cell['centerProjected'],source.canonical(cell)))
            a,b,c,d=shape(cell['geometry']).bounds;db.execute('INSERT INTO site_bounds VALUES(?,?,?,?,?)',(cursor.lastrowid,a,c,b,d))
        metadata=json.loads(db.execute("SELECT value FROM metadata WHERE key='catalog'").fetchone()[0]);metadata['extensions']=[dict(id='NGII_PARKING_CANDIDATES_V1',sha256=source.digest(evidence_raw),baseCatalogSha256=BASE_SHA,baseRecordCount=1023100,added=len(records))]
        db.execute("UPDATE metadata SET value=? WHERE key='catalog'",(source.canonical(metadata),));db.commit()
        assert db.execute('PRAGMA integrity_check').fetchone()==('ok',)
        summary=json.loads((BASE/'play-v1/summary.json').read_bytes());summary.update(playSha256=spatial.file_sha256(output/'play.sqlite'),playBytes=(output/'play.sqlite').stat().st_size,generatorSha256=spatial.file_sha256(__file__),extensionSha256=source.digest(evidence_raw),baseCatalogSha256=BASE_SHA)
        summary['counts']=dict(db.execute('SELECT status,count(*) FROM sites GROUP BY status'));summary['counts']['records']=db.execute('SELECT count(*) FROM sites').fetchone()[0]
        summary['districtKindCounts']={d+':'+k:n for d,k,n in db.execute('SELECT district_id,kind,count(*) FROM sites GROUP BY district_id,kind')}
        summary['facilityCounts']['PERMEABLE_PAVEMENT']+=len(records)
        (output/'summary.json').write_text(source.canonical(summary)+'\n')
    print(source.canonical(dict(playSha256=summary['playSha256'],counts=counts)),flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);build(p.parse_args().output.absolute())
