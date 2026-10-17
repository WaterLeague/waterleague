"""보관된 후보를 유지한 채 신규 설치의 기하 면적·직접 강우 경계 고정."""
import copy
import gzip
import hashlib
import json
from decimal import Decimal, ROUND_FLOOR
from pathlib import Path
from shapely.geometry import Polygon

ROOT=Path(__file__).resolve().parents[1]
DIRECTORY=ROOT/'backend/src/main/resources/shared-sites'

def encode(value):return (json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode()
def sha(raw):return hashlib.sha256(raw).hexdigest()
def save(path,raw):
    if path.exists() and path.read_bytes()!=raw:raise ValueError('불변 후보 덮어쓰기 거부')
    path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)

def constrain(cell):
    cell=copy.deepcopy(cell)
    shape=Polygon(cell['coordinates'])
    area=cell['areaM2']
    if not shape.is_valid or shape.is_empty or abs(shape.area-area)>max(.001,area*1e-6):
        raise ValueError('공개 도형 면적 불일치')
    limit=Decimal(str(min(shape.area,area))).quantize(Decimal('.01'),rounding=ROUND_FLOOR)
    if limit<=0:raise ValueError('후보 면적 부족')
    cell.update({'maxAreaM2':float(limit),'areaLimitBasis':'PUBLIC_FOOTPRINT_GEOMETRY',
        'siteEligibility':'UNKNOWN','inflowPolicy':'DIRECT_RAINFALL_ONLY'})
    return cell

def main():
    old_raw=(DIRECTORY/'catalog.json').read_bytes();old=json.loads(old_raw)
    if sha(old_raw)!='f26b639dbdb2fee3c1aff172a19153868a07aa70735a6dfcfda863c3a38e8b64':raise ValueError('이전 목록 해시 오류')
    regions={r['districtId']:r for r in json.loads((ROOT/'data/manifests/seoul-play-v2.json').read_text())['regions']}
    models={m['sha256']:m for m in json.loads((ROOT/'data/models/catalog.json').read_text())['models']}
    entries=[]
    for e in old['entries']:
        region=regions[e['districtId']];raw=(DIRECTORY/e['file']).read_bytes()
        if sha(raw)!=e['gzipSha256']:raise ValueError('이전 후보 압축 해시 오류')
        source=gzip.decompress(raw)
        if sha(source)!=e['sha256']:raise ValueError('이전 후보 해시 오류')
        snapshot=json.loads(source);model_raw=(ROOT/'data/models'/models[region['defaultModelHash']]['file']).read_bytes()
        if sha(model_raw)!=region['defaultModelHash']:raise ValueError('기본 모델 해시 오류')
        model=json.loads(model_raw);cells=[]
        for item in model['cells']:
            c=copy.deepcopy(item)
            c['coordinates']=[[x+region['center'][0],y+region['center'][1]] for x,y in c['coordinates']]
            c['center']=[v+region['center'][i] for i,v in enumerate(c['center'])]
            cells.append(constrain(c))
        cells += [constrain(c) for c in snapshot['cells']]
        cells.sort(key=lambda c:c['id'])
        if len({c['id'] for c in cells})!=len(cells):raise ValueError('후보 중복')
        snapshot.update({'schemaVersion':2,'cells':cells,'previousSnapshotSha256':e['sha256'],
            'constraintVersion':'GEOMETRIC_DIRECT_RAIN_V2','physicsAdapter':'CONTINUOUS_V2',
            'limitations':['공개 footprint 면적은 구조안전·피난 동선·시공 적합성 확인 결과가 아님',
                '시설 외부 유입 연결 미확인: 시설 자체 강우만 처리','토양·표면 경사·시설 재료·초기 수분은 미확인 설계 조건']})
        data=encode(snapshot);compressed=gzip.compress(data,mtime=0);name=e['districtId']+'-v2.json.gz'
        save(DIRECTORY/name,compressed)
        entries.append(e|{'file':name,'sha256':sha(data),'gzipSha256':sha(compressed),'bytes':len(data),
            'count':len(cells),'roofCount':sum(c['kind']=='ROOF' for c in cells),'groundCount':sum(c['kind']=='GROUND' for c in cells)})
    result={'schemaVersion':2,'previousCatalogSha256':sha(old_raw),'generatorSha256':sha(Path(__file__).read_bytes()),
        'constraintVersion':'GEOMETRIC_DIRECT_RAIN_V2','entries':entries}
    data=encode(result);save(DIRECTORY/'catalog-v2.json',data);save(ROOT/'data/manifests/shared-sites-v2.json',data)
    print('catalog',sha(data),'candidates',sum(e['count'] for e in entries))
if __name__=='__main__':main()
