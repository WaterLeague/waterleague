"""공개 관망의 기존 관로 연결·단면·마찰 입력 보존."""
import json
import sys
from pathlib import Path
from local_config import ROOT
sys.path.insert(0, str(ROOT/'simulation'))
from waterleague_sim.ingestion.published_network import load_archive, records, digest
from waterleague_sim.ingestion.network_variant import derive


def main():
    raw_catalog=(ROOT/'backend/src/main/resources/watersheds/seocho-published-v1.json').read_bytes()
    catalog=json.loads(raw_catalog)
    _,manifest_hash,entries=load_archive(ROOT,ROOT/'data/manifests/mendeley-seocho-network-v3.json')
    if manifest_hash!=catalog['sourceManifestSha256']: raise ValueError('공개 관망 원문 불일치')
    original=next(e['raw'] for e in entries if e['member']==catalog['sourceMember'])
    if digest(original)!=catalog['sourceOriginalSha256']: raise ValueError('공개 관망 원문 불일치')
    base,_=derive(original,catalog['numericalProfile'])
    sections=records(original)[1]
    cross={r['tokens'][0]:r for r in sections['XSECTIONS']}
    depths={r['tokens'][0]:float(r['tokens'][2]) for r in sections['JUNCTIONS']}
    conduits=[]
    for row in sections['CONDUITS']:
        t=row['tokens']; x=cross[t[0]]; v=x['tokens']
        if v[1] not in ('CIRCULAR','RECT_CLOSED'): continue
        conduits.append({'id':t[0],'fromNode':t[1],'toNode':t[2], 'lengthM':float(t[3]),
            'inletOffsetM':float(t[5]),'outletOffsetM':float(t[6]),
            'maxFullDepthM':min(depths[n]-float(offset) for n,offset in ((t[1],t[5]),(t[2],t[6])) if n in depths),
            'original':{'shape':v[1],'fullDepthM':float(v[2]),'widthM':float(v[3]) if v[1]=='RECT_CLOSED' else None,
                'barrels':int(v[6]) if len(v)>6 else 1,'roughness':float(t[4])},
            'sourceLine':row['line'],'crossSectionSourceLine':x['line'],
            'sourceConduitTokens':t,'sourceCrossSectionTokens':v})
    value={'schemaVersion':1,'id':'SEOUL_PUBLIC_NETWORK_CONDUITS_V1','facilityType':'CONDUIT',
        'sourceCatalogSha256':digest(raw_catalog),'sourceOriginalSha256':digest(original),'baseNetworkSha256':digest(base),
        'generatorSha256':digest(Path(__file__).read_bytes()),'sourceUrl':catalog['sourceUrl'],'conduits':conduits,
        'completeInstalledCostKrw':None,'designBasis':'EXPLICIT_DESIGN_NOT_SITE_MEASURED',
        'limitations':['공개 연구 모형의 기존 관로 개량 비교이며 현장 관로 대장·공사 가능성의 확인 아님',
            '원본 연결·길이·관저고·초기 유량·경계·손실 조건 유지, 단면·병렬 관 개수·Manning 조도만 설계 변경',
            '관로 높이는 공개 접속 절점 최대 깊이에서 원 관저고 오프셋을 뺀 범위 내 제한, 현장 허가 한도 아님',
            '직사각형 폐합 암거와 원형 관로만 지원, 별도 입구 통제 암거 코드는 원본 값 유지',
            '시공비·부지·매설 깊이·시설 유효 시점 미확정, 지도 점유·예산·순위 미개방']}
    data=(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode()
    target=ROOT/'backend/src/main/resources/watersheds/seocho-conduits-v1.json'
    if target.exists() and target.read_bytes()!=data: raise ValueError('기존 관로 목록 변경 금지')
    target.write_bytes(data);print(digest(data),len(conduits))


if __name__=='__main__': main()
