"""공식 피해 기록으로 선별한 서울 집중호우 창의 관측 수집·재해 모드 등록."""
import argparse
import copy
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
import pyproj
from local_config import ROOT, load
from fetch_seoul_regional_rainfall import fetch, stations_at, RAIN_URL, digest, save_json
from prepare_rainfall_catalog import statistics
sys.path.insert(0,str(ROOT/'simulation'))
from waterleague_sim.ingestion.kma import normalize
from waterleague_sim.model_catalog import read_catalog

EVENTS = [
 {'id':'seoul-20220808','title':'2022년 8월 수도권 집중호우','eventDate':'2022-08-08',
  'startKst':'202208081800','endKst':'202208082359',
  'summary':'한강 이남 도심과 저지대 지하공간에 침수 피해가 발생한 집중호우. 8일 저녁 관측 창을 재생합니다.',
  'evidenceTitle':'서울연구원 · 2022년 8월 집중호우 강우량과 피해특성',
  'evidenceUrl':'https://www.si.re.kr/bbs/view.do?key=2024100042&pstSn=2208290002'},
 {'id':'seoul-20110727','title':'2011년 7월 서울 집중호우','eventDate':'2011-07-27',
  'startKst':'201107270001','endKst':'201107271200',
  'summary':'서울 도심 침수와 우면산 산사태가 발생한 집중호우. 27일 오전 강우를 재생하며 산사태는 계산하지 않습니다.',
  'evidenceTitle':'기상청 · 2011 서울특별시 기후변화 적응정보 보고서',
  'evidenceUrl':'https://www.climate.go.kr/home/cc_data/2011_RRCC/2011_RRCC_01.pdf'},
 {'id':'seoul-20100921','title':'2010년 추석 서울 집중호우','eventDate':'2010-09-21',
  'startKst':'201009211000','endKst':'201009212000',
  'summary':'광화문 등 서울 시내 주택·도로 침수가 발생한 집중호우. 21일 낮과 저녁 관측 창을 재생합니다.',
  'evidenceTitle':'기상청 · 2011 서울특별시 기후변화 적응정보 보고서',
  'evidenceUrl':'https://www.climate.go.kr/home/cc_data/2011_RRCC/2011_RRCC_01.pdf'},
]

def payload(value): return (json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode()
def write_new(path,raw):
 if path.exists() and path.read_bytes()!=raw: raise ValueError('등록 자료 덮어쓰기 거부: '+path.name)
 path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
def rain(station,event,key):
 start,end=event['startKst'],event['endKst'];sid=station['stationId'];stem=f'kma-{sid}-{start}-{end}'
 raw=fetch(stem,RAIN_URL,{'tm1':start,'tm2':end,'stn':sid,'disp':'0','help':'1'},key)
 rows,total=normalize(raw.decode('utf-8'))
 if rows[0].start.astimezone(__import__('waterleague_sim.ingestion.kma',fromlist=['KST']).KST).strftime('%Y%m%d%H%M')!=start or rows[-1].end.astimezone(__import__('waterleague_sim.ingestion.kma',fromlist=['KST']).KST).strftime('%Y%m%d%H%M')!=end or any(r.station_id!=sid for r in rows): raise ValueError('강우 창 불일치')
 result={'id':stem+'-disaster-v1','provider':'기상청','stationId':sid,'stationName':station['stationName'],
  'sourceTimezone':'Asia/Seoul','intervalSeconds':60,'start':rows[0].start.isoformat(),'end':rows[-1].end.isoformat(),
  'depthsMm':[float(r.depth_mm) for r in rows],'totalDepthMm':float(total),'sourceHash':digest(raw),'sourceManifest':stem+'.json',
  'sourceUrl':'https://apihub.kma.go.kr/apiList.do?seqApi=2&seqApiSub=239',
  'attribution':'기상청 기상자료개방포털 · AWS 매분 관측자료',
  'checks':['분 간격 연속성','누적 강우 비음수 차분','15분·60분 이동 누적 일치','요청 관측소·시간 일치'],
  'stationMetadata':station,'windowType':'OBSERVED_WINDOW_NOT_COMPLETE_STORM','windowStatistics':statistics(rows),
  'quality': 'BASIC_CHECKED','limitations':['실제 재해 기간 중 명시한 관측 창만 재생; 완전한 재해 사상 아님','원문 누적값·이동합 자체 일관성 검사; 별도 품질 플래그 미제공','관측 창 밖 무강우·결측 보간 없음','현재 공개 형상에 과거 강우를 적용한 비교이며 당시 피해·수심 복원 아님']}
 save_json(ROOT/'data/derived/rainfall'/f'{result["id"]}.json',result)
 return result

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--event',choices=[e['id'] for e in EVENTS]);args=parser.parse_args()
 load();key=os.environ['KMA_API_KEY']
 regions=json.loads((ROOT/'data/manifests/seoul-play-v2.json').read_text())['regions'];base_models=read_catalog(ROOT/'data/models')
 catalog=json.loads((ROOT/'data/models/catalog.json').read_text());maps=json.loads((ROOT/'frontend/public/data/maps.json').read_text());geod=pyproj.Geod(ellps='WGS84')
 output=[]
 for event in EVENTS:
  manifest=ROOT/'data/manifests'/f'{event["id"]}-selection-v1.json'
  if manifest.exists(): selections=json.loads(manifest.read_text())['selections']
  elif args.event and args.event!=event['id']: selections=[]
  else:
   selections=[]
   try:
    first,last=stations_at(event['startKst'],key),stations_at(event['endKst'],key)
    planned=[]
    for region in regions:
     lon,lat=json.loads((ROOT/'frontend/public/data'/region['mapFile']).read_text())['origin']
     candidates=[]
     for distance,sid in sorted((geod.inv(lon,lat,s['longitude'],s['latitude'])[2]/1000,s['stationId']) for s in first.values()):
      station=copy.deepcopy(first[sid]);final=last.get(sid)
      if distance>10 or not final or any(station[k]!=final[k] for k in ('longitude','latitude','elevationM')):continue
      station.update({'endTimeKst':event['endKst'],'endSourceSha256':final['sourceSha256'],'endSourceManifest':final['sourceManifest']})
      candidates.append((station,round(distance,3)))
     planned.append((region,candidates))
    with ThreadPoolExecutor(max_workers=3) as executor:
     futures={}
     for region,candidates in planned:
      if not candidates:continue
      station,distance=candidates[0]
      sid=station['stationId']
      if sid not in futures:futures[sid]=executor.submit(rain,station,event,key)
     for region,candidates in planned:
      selection={'districtId':region['districtId'],'districtName':region['districtName'],'status':'REJECTED','rejectedStations':[]}
      for station,distance in candidates:
       sid=station['stationId']
       if sid not in futures:futures[sid]=executor.submit(rain,station,event,key)
       try:
        observed=futures[sid].result();selection.update({'status':'ACCEPTED','stationId':sid,'stationDistanceKm':distance,'rainfallId':observed['id'],'rainfallSha256':digest(payload(observed))});break
       except Exception as e:selection['rejectedStations'].append({'stationId':sid,'distanceKm':distance,'reason':str(e)[:140]})
      selections.append(selection);print(event['id'],region['districtName'],selection['status'],selection.get('stationId'),len(selection['rejectedStations']),flush=True)
    # 실패가 있으면 재실행 시 원본 캐시를 이용해 해당 자료까지 다시 확인.
    if len(selections)==25 and all(s['status']=='ACCEPTED' for s in selections):save_json(manifest,{'event':event,'selectionRule':'NEAREST_QUALITY_ACCEPTED_STABLE_AWS_WITHIN_10KM','selections':selections})
   except Exception as e:print(event['id'],'SOURCE_UNAVAILABLE',str(e)[:140],flush=True)
  bindings=[]
  for selection in selections:
   if selection['status']!='ACCEPTED':continue
   region=next(r for r in regions if r['districtId']==selection['districtId'])
   raw=(ROOT/'data/derived/rainfall'/f'{selection["rainfallId"]}.json').read_bytes()
   if digest(raw)!=selection['rainfallSha256']:raise ValueError('재해 강우 해시 불일치')
   observed=json.loads(raw);observed['stationDistanceKm']=selection['stationDistanceKm'];observed['stationDistanceEvidence']='대표 블록에서 10km 이내·관측 창 검사 통과·양 끝 좌표 동일한 AWS 중 가장 가까운 지점; 구 전체 대표성 미검증'
   model=json.loads(base_models[region['defaultModelHash']]);identifier=region['mapId']+'-disaster-'+event['eventDate'].replace('-','')
   model.update({'id':identifier,'title':region['districtName']+' · '+event['title'],'rainfall':observed,'rainfallSource':'기상청 '+observed['stationName']+' '+observed['stationId']+' · '+event['eventDate'],
    'disasterEvent':event,'regionalRainfallUse':'NEAREST_AWS_OBSERVED_REPLAY',
    'assumptions':[s for s in model['assumptions'] if '2024' not in s and '후행 무강우' not in s and '성동 관측 강우 공통' not in s]+['현재 공개 형상과 과거 재해 강우의 가상 시설 비교; 당시 지형·피해 복원 아님','시설 재료·토양·초기 수분·경사 미확인 설계 조건']})
   for field in ('rainfallModelGeneratorSha256','rainfallSelectionManifestSha256'):model.pop(field,None)
   encoded=payload(model);entry={'id':identifier,'file':identifier+'.json','sha256':digest(encoded)}
   for folder in ('data/models','backend/src/main/resources/models'):write_new(ROOT/folder/entry['file'],encoded)
   existing=next((m for m in catalog['models'] if m['id']==identifier),None)
   if existing and existing!=entry:raise ValueError('기존 사건 모델 변경 거부')
   if not existing:catalog['models'].append(entry)
   binding=next(m for m in maps['maps'] if m['id']==region['mapId'])['modelHashes']
   if entry['sha256'] not in binding:binding.append(entry['sha256'])
   bindings.append({'districtId':region['districtId'],'modelHash':entry['sha256'],'stationName':observed['stationName'],'stationId':observed['stationId'],'totalDepthMm':observed['totalDepthMm']})
  output.append(event|{'models':bindings})
 if any(len(e['models'])!=25 for e in output):raise ValueError('25개 구의 유효 관측 확보 전 재해 카탈로그 게시 거부')
 for folder in ('data/models','backend/src/main/resources/models'):(ROOT/folder/'catalog.json').write_bytes(payload(catalog))
 (ROOT/'frontend/public/data/maps.json').write_bytes(payload(maps))
 target=ROOT/'backend/src/main/resources/disasters/seoul-events-v1.json';target.parent.mkdir(exist_ok=True);target.write_bytes(payload({'schemaVersion':1,'events':output}))
 print('REGISTERED',[(e['id'],len(e['models'])) for e in output],flush=True)
if __name__=='__main__':main()
