"""기존 브이월드 권한으로 서울 심토토성 공개 원문을 페이지별 보관."""
import hashlib,json,os
from datetime import datetime,timezone
from urllib.request import Request,build_opener
from urllib.parse import urlencode
from pathlib import Path
from local_config import ROOT,load
from probe_vworld import NoRedirect

def main():
    load();key=os.environ['VWORLD_API_KEY'];domain=os.environ.get('VWORLD_DOMAIN','http://127.0.0.1:5173')
    out=ROOT/'data/private/seoul-soil-20261018';out.mkdir(parents=True,exist_ok=True)
    records=[];total=None;seen=set();page=1
    while total is None or len(seen)<total:
        target=out/f'deepsoil-page-{page}.json'
        if target.exists():raw=target.read_bytes()
        else:
            p={'service':'data','version':'2.0','request':'GetFeature','data':'LT_C_ASITDEEPSOIL','geomFilter':'BOX(126.76,37.41,127.19,37.71)','size':'1000','page':str(page),'format':'json','crs':'EPSG:4326','key':key,'domain':domain}
            try:
                with build_opener(NoRedirect).open(Request('https://api.vworld.kr/req/data?'+urlencode(p),headers={'Referer':domain+'/'}),timeout=30) as response:raw=response.read(20_000_001)
            except Exception:raise SystemExit('공개 토성 조회 실패: 인증 URL 출력 생략') from None
        if len(raw)>20_000_000 or key.encode() in raw:raise ValueError('토성 응답 검사 실패')
        value=json.loads(raw)['response']
        if value['status']!='OK':raise ValueError('토성 조회 거부')
        count=int(value['record']['total']);features=value['result']['featureCollection']['features']
        if total is not None and total!=count:raise ValueError('조회 중 자료 수 변경')
        total=count
        if not features or int(value['record']['current'])!=len(features):raise ValueError('토성 페이지 누락')
        for f in features:
            if f['id'] in seen:raise ValueError('토성 페이지 중복')
            seen.add(f['id'])
        target.write_bytes(raw)
        records.append({'file':str(target.relative_to(ROOT)),'sha256':hashlib.sha256(raw).hexdigest(),'count':len(features),'bytes':len(raw)})
        print('심토토성',len(seen),'/',total,flush=True);page+=1
        if page>30:raise ValueError('토성 요청 상한 초과')
    if len(seen)!=total:raise ValueError('토성 전체 자료 수 불일치')
    manifest=ROOT/'data/manifests/seoul-soil-20261018.json'
    value={'schemaVersion':1,'acquiredAt':datetime.now(timezone.utc).isoformat(),'provider':'국립농업과학원 / 브이월드','layer':'LT_C_ASITDEEPSOIL','sourceUrl':'https://www.vworld.kr/dev/v4dv_2ddataguide2_s002.do?svcIde=asitdeepsoil&apiVer=2','bbox':[126.76,37.41,127.19,37.71],'crs':'EPSG:4326','total':total,'pages':records}
    if manifest.exists():
        # 같은 원문 재검사는 최초 수집 시각과 이미 참조된 manifest 해시를 보존한다.
        prior=json.loads(manifest.read_bytes());value['acquiredAt']=prior['acquiredAt']
        if prior!=value:raise ValueError('기존 토성 manifest와 원문 불일치')
    else:manifest.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
if __name__=='__main__':main()
