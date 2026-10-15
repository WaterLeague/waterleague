"""실제 SWMM으로 CPU 기준안 생성. 평가 강우는 탐색 종료 후에만 사용."""
from pathlib import Path
from datetime import datetime, timezone
import sys
import json
import hashlib
import tempfile
import time
import platform
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'simulation'))
from waterleague_sim.model_catalog import read_catalog
from waterleague_sim.reference.search import search, cost, key
from waterleague_sim.reference import search as algorithm
from waterleague_sim.engine import swmm


def digest(data): return hashlib.sha256(data).hexdigest()
def write(path,value): path.write_text(json.dumps(value,ensure_ascii=False,allow_nan=False,indent=2)+'\n')


def main():
    sources=read_catalog(ROOT/'data/models')
    models={h:json.loads(data) for h,data in sources.items()}
    training_hash=next(h for h,m in models.items() if m['id']=='seongsu-421-20240718')
    training=models[training_hash]
    for model in models.values():
        for field in ['cells','unitCosts','budget','maxPlacements','hydrology','generatorSha256','engineRevision']:
            if model[field]!=training[field]: raise ValueError('서로 다른 물리 조건 비교 거부')
    builder_hash=digest(Path(swmm.__file__).read_bytes())
    if builder_hash!=training['generatorSha256']:raise ValueError('빌더 버전 불일치')
    algorithm_hash=digest(Path(algorithm.__file__).read_bytes())
    runner_hash=digest(Path(__file__).read_bytes())
    identity=digest((training_hash+algorithm_hash+runner_hash).encode())
    root=ROOT/'data/private/references'/identity
    root.mkdir(parents=True,exist_ok=False)
    started=time.perf_counter();cache={};ledger=[];plans=[]
    with tempfile.TemporaryDirectory() as tmp:
        def evaluate(placements):
            k=key(placements)
            if k in cache:return cache[k]
            if len(cache)>=2000:raise ValueError('전체 고유 후보 2000회 상한')
            metrics=swmm.run(training,placements,tmp,'candidate')
            cache[k]=metrics['accountedDischargeM3']
            ledger.append({'placements':placements,'cost':int(cost(training,placements)),'accountedDischargeM3':metrics['accountedDischargeM3'],'runoffContinuityPercent':metrics['runoffContinuityPercent']})
            return cache[k]
        for budget in [30000000,100000000,300000000]:
            plan=search(training,budget,evaluate)
            plan.update({'id':f'cpu-{budget}','budget':budget,'title':f'{budget//10000:,}만 원 상한 CPU 기준안'})
            plan['candidateEvaluations']=plan.pop('evaluations')
            plans.append(plan)
            print('탐색',budget,'원','채택',len(plan['stages']),'단계','계산',plan['candidateEvaluations'],'회','지출',plan['cost'],'원',flush=True)
    search_completed=datetime.now(timezone.utc).isoformat()
    # 모든 배치를 확정한 뒤에만 별도 강우의 성능을 산출한다.
    for plan in plans:
        evaluations=[]
        for h,model in models.items():
            path=root/plan['id']/model['id'];path.mkdir(parents=True)
            (path/'model-source.json').write_bytes(sources[h])
            result=swmm.experiment(model,plan['placements'],path)
            evaluations.append({'modelHash':h,'modelTitle':model['title'],'role':'SEARCH_INPUT' if h==training_hash else 'POST_SELECTION_COMPARISON','rainfall':{k:model['rainfall'][k] for k in ['stationId','stationName','start','end','totalDepthMm']},
                'score':result['score'],'baseline':{k:v for k,v in result['baseline'].items() if k!='seriesM3s'},'strategy':{k:v for k,v in result['strategy'].items() if k!='seriesM3s'},'sensitivity':result['sensitivity'],
                'resultSha256':digest((path/'result.json').read_bytes()),'manifestSha256':digest((path/'manifest.json').read_bytes())})
        plan['evaluations']=evaluations
        plan['sampleScoreRange']={'min':min(e['score'] for e in evaluations),'max':max(e['score'] for e in evaluations)}
        print('강우 비교 완료',plan['id'],plan['sampleScoreRange'],flush=True)
    write(root/'search-ledger.json',ledger)
    report={'schemaVersion':1,'id':identity,'kind':'CPU_REFERENCE','official':False,'validationLevel':'EXPLORATORY','currency':'KRW',
        'algorithm':'GREEDY_MARGINAL_DISCHARGE_PER_KRW_V1','stepAreaM2':10,'trainingModelHash':training_hash,
        'algorithmSha256':algorithm_hash,'runnerSha256':runner_hash,'generatorSha256':builder_hash,'engineRevision':swmm.REVISION,'engineBinarySha256':digest(swmm.library_path().read_bytes()),'platform':platform.platform(),
        'modelHashes':list(models),'searchCompletedAt':search_completed,'createdAt':datetime.now(timezone.utc).isoformat(),'elapsedSeconds':round(time.perf_counter()-started,3),
        'uniqueCandidateEvaluations':len(ledger),'totalCandidateRequests':sum(p['candidateEvaluations'] for p in plans),
        'ledgerSha256':digest((root/'search-ledger.json').read_bytes()),'plans':plans,
        'limitations':['10m² 증분·시설 유형 교체 없는 탐욕 탐색. 전역 최적해 아님','탐색 중 한 강우만 사용; 별도 강우 비교도 현장 관측 검증 아님','사람과 탐색 횟수가 다름; 사람 순위에 포함하지 않음','증발·설치 가능성·토양·유입 경로 가정 유지','제시 범위는 선택된 강우 창의 최저/최고이며 신뢰구간 아님']}
    # 후보 요청 횟수와 최종 강우 계산 횟수를 구분한다.
    report['totalCandidateRequests']=sum(p['candidateEvaluations'] for p in plans)
    write(root/'report.json',report)
    (ROOT/'data/derived/cpu-search-ledger.json').write_bytes((root/'search-ledger.json').read_bytes())
    (ROOT/'backend/src/main/resources/models/cpu-search-ledger.json').write_bytes((root/'search-ledger.json').read_bytes())
    destination=ROOT/'data/derived/cpu-reference.json';destination.write_bytes((root/'report.json').read_bytes())
    (ROOT/'backend/src/main/resources/models/cpu-reference.json').write_bytes(destination.read_bytes())
    print('CPU 기준안 생성 완료',len(ledger),'고유 후보',report['elapsedSeconds'],'초',flush=True)


if __name__=='__main__':main()
