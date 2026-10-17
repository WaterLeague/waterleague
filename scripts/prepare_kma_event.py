"""수집 원본의 연속 구간 검증 및 출처 포함 파생자료 작성."""
from pathlib import Path
import sys,json,hashlib
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'simulation'))
from waterleague_sim.ingestion.kma import normalize
raw=ROOT/'data/raw/kma-108-202407180500-202407182359.txt'
rows,total=normalize(raw.read_text())
event={'id':'kma-108-20240718-0500-2359','provider':'기상청','stationId':'108','stationName':'서울','stationDistanceKm':8.1,'stationDistanceEvidence':'관측소 대표 좌표와 성수동 중심의 근사 거리; 현장 강우 대표성 미검증',
 'start':rows[0].start.isoformat(),'end':rows[-1].end.isoformat(),'sourceTimezone':'Asia/Seoul','intervalSeconds':60,'depthsMm':[float(r.depth_mm) for r in rows],'totalDepthMm':float(total),
 'evidence':'DERIVED_FROM_OBSERVED_CUMULATIVE_RAINFALL','quality':'BASIC_CHECKED_NO_PROVIDER_QC_FLAGS','sourceHash':hashlib.sha256(raw.read_bytes()).hexdigest(),
 'transformSha256':hashlib.sha256((ROOT/'simulation/waterleague_sim/ingestion/kma.py').read_bytes()).hexdigest(),
 'checks':['1분 연속성','음수·결측 거부','동일 관측소','자정 경계 제외','15분·60분 이동누적 교차검증'],
 'limitations':['관측소 강우와 성수동 현장 강우 차이 미검증','선행 강우·초기 토양수분 보정 없음','별도 기상청 품질 플래그 미제공; 자체 일관성 검사만 통과','관측기간을 벗어난 강우의 0값 보간 없음'],
 'sourceUrl':'https://apihub.kma.go.kr/apiList.do?seqApi=2&seqApiSub=239','attribution':'출처: 기상청, AWS 매분자료; 일 누적 강우 차분 처리'}
event_path=ROOT/'data/derived/kma-event.json';event_path.parent.mkdir(exist_ok=True);event_path.write_text(json.dumps(event,ensure_ascii=False,indent=2)+'\n')
modelpath=ROOT/'data/models/seongsu-lab.json';model=json.loads(modelpath.read_text());model['rainfall']=event;model['generatorSha256']=hashlib.sha256((ROOT/'simulation/waterleague_sim/engine/swmm.py').read_bytes()).hexdigest();model['rainfallSource']='기상청 서울 108 관측소 · 2024.07.18';model['simulationAvailable']=True
model['assumptions']=[s for s in model['assumptions'] if not s.startswith('2024-07-18')]
model['assumptions'].append('2024-07-18 05:00~23:59 KST 고정 비교; 마지막 강우 15:40 이후 8시간 19분 관측 무강우 포함')
modelpath.write_text(json.dumps(model,ensure_ascii=False,indent=2)+'\n');(ROOT/'backend/src/main/resources/models/seongsu-lab.json').write_bytes(modelpath.read_bytes())
(ROOT/'frontend/public/data/kma-event.json').write_bytes(event_path.read_bytes())
print('검증 통과:',len(rows),'분, 총강우',total,'mm; 탐색 등급 유지')
