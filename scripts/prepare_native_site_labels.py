"""설치 후보에 원 건물·도로 명칭과 확인 가능한 도로명 주소를 결속한다."""
import argparse,gzip,json,sqlite3
from collections import defaultdict,Counter
from contextlib import closing
from pathlib import Path
import shapely
from shapely.geometry import Point
from shapely.strtree import STRtree
import prepare_seoul_topography as source
import prepare_seoul_spatial as spatial
BASE=source.ROOT/'data/private/vworld-seoul-topography-20260307'
PLAY_SHA='4ec7535e7cbaf41dc73f73519d77ba11f956f4c75c1a574fffa08f16625919b7'
def clean(value):
    return value.strip() if isinstance(value,str) and value.strip() and len(value)<=160 else None
def build(output):
    if output.exists():raise ValueError('기존 명칭 묶음 덮어쓰기 금지')
    if spatial.file_sha256(BASE/'play-v1/play.sqlite')!=PLAY_SHA:raise ValueError('후보 원본 불일치')
    city=json.loads((source.ROOT/'frontend/public/data/seoul-native-v1/city.json').read_bytes())
    districts={d['id']:d['name'] for d in city['districts']}
    roads=[];road_names=[];seen=set()
    with closing(sqlite3.connect('file:'+str(BASE/'spatial-v1/spatial.sqlite')+'?mode=ro&immutable=1',uri=True)) as db:
        for raw,props in db.execute("SELECT geometry_wkb,properties FROM features WHERE layer='N1L_A0020000' AND geometry_status='VALID' AND deleted=0 ORDER BY fid"):
            p=json.loads(props);name=clean(p.get('도로명'))
            if name and raw not in seen:
                seen.add(raw);roads.append(shapely.from_wkb(raw));road_names.append(name)
    tree=STRtree(roads);print('원 도로 명칭 준비',len(roads),flush=True)
    groups=defaultdict(dict);numbers=Counter();counts=Counter()
    with closing(sqlite3.connect('file:'+str(BASE/'play-v1/play.sqlite')+'?mode=ro&immutable=1',uri=True)) as db:
        db.execute('ATTACH DATABASE ? AS originals',('file:'+str(BASE/'objects-v1/objects.sqlite')+'?mode=ro&immutable=1',))
        rows=db.execute('''SELECT s.id,s.district_id,s.kind,s.role,s.cx,s.cy,v.properties FROM sites s
            JOIN originals.attribute_variants v ON v.object_id=s.object_id
            WHERE s.allowed_mask<>0 AND v.sha256=(SELECT MIN(sha256) FROM originals.attribute_variants WHERE object_id=s.object_id)
            ORDER BY s.district_id,s.kind,s.role,s.id''')
        for identifier,district,kind,role,x,y,raw in rows:
            props=json.loads(raw);number_key=(district,role);numbers[number_key]+=1
            name=clean(props.get('명칭')) or (clean(props.get('주기')) if kind=='ROOF' else None)
            road=clean(props.get('도로명'));address=None
            if kind!='ROOF' and not road:
                nearest=tree.query_nearest(Point(x,y),max_distance=30,return_distance=True)
                if len(nearest[0]):
                    chosen=min(zip(nearest[1],nearest[0]),key=lambda pair:(float(pair[0]),road_names[int(pair[1])],int(pair[1])))
                    road=road_names[int(chosen[1])];counts['nearbySourceRoadNames']+=1
            if road:
                address='서울특별시 '+districts[district]+' '+road
                main=props.get('건물본번');sub=props.get('건물부번')
                if kind=='ROOF' and str(main).isdigit() and int(main)>0:
                    address+=' '+str(int(main))
                    if str(sub).isdigit() and int(sub)>0:address+='-'+str(int(sub))
                elif kind=='ROOF':address=None
            noun={'BUILDING_FOOTPRINT':'옥상','ROAD_AREA':'도로','SIDEWALK_AREA':'보도','CULTIVATION_LANDSCAPE_AREA':'녹지'}.get(role,'지상')
            base=(name or road or ('건물' if kind=='ROOF' else ''))
            title=((base+' ') if base else '')+noun+' · '+str(numbers[number_key])
            groups[identifier[1:3]][identifier]=dict(name=title,address=address)
            counts['labels']+=1;counts['named']+=bool(name or road);counts['address']+=bool(address)
    output.mkdir(parents=True);entries={}
    for prefix,labels in sorted(groups.items()):
        raw=(source.canonical(labels)+'\n').encode();packed=gzip.compress(raw,mtime=0)
        filename=prefix+'.json.gz';(output/filename).write_bytes(packed)
        entries[prefix]=dict(file=filename,sha256=source.digest(raw),bytes=len(raw),storedSha256=source.digest(packed),storedBytes=len(packed),count=len(labels))
    index=dict(schemaVersion=1,sourceCatalogSha256=PLAY_SHA,sourceSpatialSha256=spatial.file_sha256(BASE/'spatial-v1/spatial.sqlite'),sourceObjectsSha256=spatial.file_sha256(BASE/'objects-v1/objects.sqlite'),generatorSha256=spatial.file_sha256(__file__),counts=dict(counts),parts=entries,
        policy=dict(numberBasis='DISTRICT_ROLE_CANDIDATE_ID_ORDER',roadNameSearchMaximumM=30,roadLocationIsBuildingAddress=False,hydraulicInputsChanged=False))
    (output/'index.json').write_text(source.canonical(index)+'\n');print(source.canonical(dict(indexSha256=spatial.file_sha256(output/'index.json'),**counts)),flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);build(p.parse_args().output.absolute())
