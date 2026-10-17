"""수치지형도 v2의 실제 SWMM 기준안 생성. 기존 OSM 산출물 보존."""
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
    models={h:json.loads(data) for h,data in sources.items() if json.loads(data).get('mapId')=='seongsu-ngii-2025-v2'}
    if len(models)!=4: raise ValueError('수치지형도 비교 모델 4개 필요')
    training_hash=next(h for h,m in models.items() if m['id']=='seongsu-ngii-v2-421-20240718')
    training=models[training_hash]
    for model in models.values():
        for field in ['cells','unitCosts','budget','maxPlacements','hydrology','generatorSha256','engineRevision','geometrySourceHash','mapSnapshotHash']:
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
        'mapId':training['mapId'],'mapTitle':training['mapTitle'],'geometrySourceHash':training['geometrySourceHash'],
        'modelHashes':list(models),'searchCompletedAt':search_completed,'createdAt':datetime.now(timezone.utc).isoformat(),'elapsedSeconds':round(time.perf_counter()-started,3),
        'uniqueCandidateEvaluations':len(ledger),'totalCandidateRequests':sum(p['candidateEvaluations'] for p in plans),
        'ledgerSha256':digest((root/'search-ledger.json').read_bytes()),'plans':plans,
        'limitations':['10m² 증분·시설 유형 교체 없는 탐욕 탐색. 전역 최적해 아님','탐색 중 한 강우만 사용; 별도 강우 비교도 현장 관측 검증 아님','사람과 탐색 횟수가 다름; 사람 순위에 포함하지 않음','증발·설치 가능성·토양·유입 경로 가정 유지','제시 범위는 선택된 강우 창의 최저/최고이며 신뢰구간 아님']}
    # 후보 요청 횟수와 최종 강우 계산 횟수를 구분한다.
    report['totalCandidateRequests']=sum(p['candidateEvaluations'] for p in plans)
    write(root/'report.json',report)
    for target, source_file in [('cpu-search-ledger-ngii-v2.json', root/'search-ledger.json'),
                                ('cpu-reference-ngii-v2.json', root/'report.json')]:
        for directory in ['data/derived', 'backend/src/main/resources/models']:
            path=ROOT/directory/target
            if path.exists() or path.is_symlink(): raise ValueError('기존 기준안 덮어쓰기 거부')
            with path.open('xb') as stream: stream.write(source_file.read_bytes())
    entries=[]
    for report_file, ledger_file in [('cpu-reference.json','cpu-search-ledger.json'),
                                      ('cpu-reference-ngii-v2.json','cpu-search-ledger-ngii-v2.json')]:
        raw=(ROOT/'data/derived'/report_file).read_bytes()
        doc=json.loads(raw)
        entries.append({'reportFile':report_file,'ledgerFile':ledger_file,'reportSha256':digest(raw),
                        'modelHashes':doc['modelHashes']})
    for directory in ['data/derived','backend/src/main/resources/models']:
        path=ROOT/directory/'reference-catalog.json'
        if path.exists() or path.is_symlink(): raise ValueError('기준안 목록 덮어쓰기 거부')
        write(path, {'schemaVersion':1,'references':entries})
    print('CPU 기준안 생성 완료',len(ledger),'고유 후보',report['elapsedSeconds'],'초',flush=True)


if __name__=='__main__':main()
