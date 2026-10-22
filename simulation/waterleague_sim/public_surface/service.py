"""고정 공개 모형의 직렬 실행, 재시작 계보, 원자적 최신 결과 게시."""
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid

from waterleague_sim.engine.flood_errors import FloodModelError, require
from waterleague_sim.evaluation.coupled_adapter import engine_signature, read_coupled_record
from waterleague_sim.evaluation.exception import EvaluationError
from waterleague_sim.evaluation.values import digest, is_hash
from waterleague_sim.forcing.observed_rainfall import utc
from waterleague_sim.presentation.surface_playback import export_playback
from . import repository as repo
from .recipe import request
from waterleague_sim.job_runtime import run_process


def now():
    return datetime.now(timezone.utc)


def recent(at, clock):
    return clock-timedelta(minutes=5)<=at<=clock


def index_update(artifacts, model, row, models, clock):
    root=repo.safe_path(artifacts,'public-surface')
    with repo.locked(root/'index.lock',blocking=True):
        path=root/'current.json'
        value=repo.decode(repo.read(path,maximum=256000)) if path.exists() else {'schemaVersion':1,'runs':[]}
        require(isinstance(value,dict) and value.get('schemaVersion')==1 and isinstance(value.get('runs'),list)
                and len(value['runs'])<=128 and all(isinstance(r,dict) for r in value['runs']),
                'PUBLIC_SURFACE_INDEX_INVALID')
        rows=[]; found=set()
        for old in value['runs']:
            basin=old.get('basinId')
            require(basin not in found,'PUBLIC_SURFACE_INDEX_DUPLICATE')
            found.add(basin)
            if basin==model['id']:
                if row is not None:
                    require(utc(old['lastFrameAt'])<=utc(row['lastFrameAt']), 'PUBLIC_SURFACE_PUBLICATION_REVERSED')
                continue
            if basin in models and recent(utc(old['lastFrameAt']),clock):rows.append(old)
        if row is not None:
            require(recent(utc(row['lastFrameAt']),clock),'PUBLIC_SURFACE_RESULT_EXPIRED')
            rows.append(row)
        repo.atomic_json(path,{'schemaVersion':1,'runs':sorted(rows,key=lambda r:r['basinId'])})


def snapshot(directory,bundle,manifest):
    # 현재 지도가 없거나 변조됐으면 계산 전에 중단하며 이전 공간으로 대체하지 않는다.
    city_raw, _ = repo.city_source(repo.ROOT)
    city_target = repo.safe_path(directory/'source', repo.CITY_FILE)
    city_target.parent.mkdir(parents=True, exist_ok=True)
    city_target.write_bytes(city_raw)
    for name,expected in manifest['files'].items():
        target=repo.safe_path(directory/'input-bundle',name)
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(repo.read(repo.safe_path(bundle,name),expected=expected))
    (directory/'input-bundle/manifest.json').write_bytes(repo.read(bundle/'manifest.json'))
    sources=list((repo.ROOT/'simulation/waterleague_sim').rglob('*.py'))
    sources+=list((repo.ROOT/'simulation/native').glob('*.inc'))
    sources+=[repo.ROOT/name for name in ('simulation/uv.lock','simulation/pyproject.toml',
        'scripts/run_public_surface.py','scripts/local_config.py',
        'scripts/build_rainfall_swmm.py','scripts/build_network_swmm.py','scripts/build_live_swmm.py',
        'data/manifests/anuga-4.0.1.json')]
    for engine in ('network-rainfall-swmm','network-metrics-swmm','network-exchange-swmm'):
        sources+=list((repo.ROOT/f'tmp/{engine}-build/install/bin').glob('*'))
    for source in sources:
        if source.is_file():
            target=directory/'source'/source.relative_to(repo.ROOT)
            target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)


def run_engine(directory):
    environment={k:v for k,v in os.environ.items() if k in ('PATH','LANG','LC_ALL','HOME','TMPDIR','KMA_API_KEY','EXTERNAL_REQUEST_STATE_DIR')}
    environment['PYTHONPATH']=str(repo.ROOT/'simulation')
    try:
        code=run_process([sys.executable,'-m','waterleague_sim.public_surface.run_job',str(directory)],
                         env=environment, timeout=120)
    except subprocess.TimeoutExpired:
        raise FloodModelError('PUBLIC_SURFACE_CALCULATION_TIMEOUT') from None
    completion=repo.decode(repo.read(directory/'completion.json',maximum=4096)) if (directory/'completion.json').exists() else {}
    require(code==0 and completion.get('status')=='SUCCEEDED', 'PUBLIC_SURFACE_CALCULATION_FAILED')


def publication(model,directory,identifier,token,cutoff,clock):
    raw=repo.read(directory/'calculation/coupled-result.json')
    result=repo.decode(raw)
    require(result.get('numericalStatus')=='PASSED' and result.get('classification')==repo.CLASSIFICATION
            and result.get('observedRainfall',{}).get('directResponse',{}).get('method')=='KMA_AWS_DIRECT_RESPONSE_V1',
            'PUBLIC_SURFACE_RESULT_INVALID')
    payload=repo.decode(repo.read(directory/'request.json'))
    saved=repo.decode(repo.read(directory/'calculation/coupled-input.json'))
    forcing=saved.get('observedRainfall',{})
    require({k:v for k,v in saved.items() if k!='observedRainfall'}==payload['model']
            and all(forcing.get(k)==v for k,v in payload['rainfall'].items()),
            'PUBLIC_SURFACE_RESULT_INPUT_MISMATCH')
    network=repo.decode(repo.read(directory/'calculation/network/network-result.json'))
    surface_result=repo.decode(repo.read(directory/'calculation/surface/surface-result.json'))
    policy=repo.decode(repo.read(directory/'input-bundle/numerical-policy.json',
                                 expected=model['numericalPolicySha256']))
    require(policy.get('engineSha256')==engine_signature(network,surface_result,result),
            'PUBLIC_SURFACE_ENGINE_POLICY_MISMATCH')
    context={'scopeId':'PUBLIC_CURRENT_BASELINE_ONLY','modelGrade':'EXPLORATORY',
        'evidenceClass':'PUBLIC_DATA','comparisonKind':'CURRENT','effectAreaId':model['id'],
        'scenarioSnapshotSha256':model['inputBundleSha256'],'forcingSha256':digest(forcing),
        'engineSha256':policy['engineSha256'],'metricSpecificationSha256':digest(saved['evaluationMetrics'])}
    try:
        verified=read_coupled_record(directory/'calculation',repo.sha(raw),context)
    except EvaluationError:
        raise FloodModelError('PUBLIC_SURFACE_RESULT_INTEGRITY_FAILED') from None
    require(verified['complete'],'PUBLIC_SURFACE_RESULT_INCOMPLETE')
    _, city = repo.city_source(directory/'source')
    surface=directory/'calculation/surface'
    result_hash=repo.sha(repo.read(surface/'surface-result.json'))
    descriptor=export_playback(surface,result_hash,directory/'surface-playback',city)
    catalog=repo.decode(repo.read(directory/'surface-playback/catalog.json',expected=descriptor['catalogSha256']))
    final=utc(catalog['startUtc'])+timedelta(seconds=catalog['frames'][-1]['timeSeconds'])
    require(catalog['classification']==model['classification'] and final==cutoff and recent(final,clock)
            and catalog['originProjected']==[198128.,551989.], 'PUBLIC_SURFACE_RESULT_EXPIRED_OR_UNBOUND')
    mesh=repo.decode(repo.read(directory/'surface-playback/mesh.json',expected=catalog['mesh']['sha256']))
    xmin,ymin,xmax,ymax=model['bounds']
    require(all(xmin<=x<=xmax and ymin<=y<=ymax for x,y in mesh['vertices']),
            'PUBLIC_SURFACE_RESULT_OUTSIDE_MODEL')
    return {'id':str(identifier),'token':str(token),'basinId':model['id'],'scenario':'PUBLIC_BASELINE',
        'numericalStatus':'PASSED','forcingSource':'OFFICIAL_OBSERVATIONS',
        'inputBundleSha256':model['inputBundleSha256'],'numericalPolicySha256':model['numericalPolicySha256'],
        'lastFrameAt':final.isoformat(),'catalogSha256':descriptor['catalogSha256'],'surfaceResultSha256':result_hash}


def recover_previous(root, model, state):
    path=root/'current.json'
    if not path.exists():return state
    index=repo.decode(repo.read(path,maximum=256000))
    require(isinstance(index,dict) and index.get('schemaVersion')==1 and isinstance(index.get('runs'),list)
            and len(index['runs'])<=128 and all(isinstance(r,dict) for r in index['runs']),
            'PUBLIC_SURFACE_INDEX_INVALID')
    rows=[r for r in index['runs'] if r.get('basinId')==model['id']]
    require(len(rows)<=1,'PUBLIC_SURFACE_INDEX_DUPLICATE')
    if not rows:return state
    row=rows[0]
    previous=state.get('previous')
    if previous and utc(previous['lastFrameAt'])>=utc(row['lastFrameAt']):return state
    require(row['inputBundleSha256']==model['inputBundleSha256']
            and row['numericalPolicySha256']==model['numericalPolicySha256'],
            'PUBLIC_SURFACE_ORIGIN_CHANGE_REQUIRES_NEW_MODEL')
    directory=repo.safe_path(root,f"{uuid.UUID(row['id'])}/{uuid.UUID(row['token'])}")
    manifest=repo.decode(repo.read(directory/'manifest.json',expected=row['runManifestSha256']))
    expected=manifest['files']['calculation/coupled-input.json']
    repo.read(directory/'calculation/coupled-input.json',expected=expected)
    return state | {'previous':row | {'inputSha256':expected}}


def run_once(artifacts, *, clock=now):
    artifacts=Path(artifacts).resolve()
    models=repo.load_registry()
    worked=False
    for model in models.values():
        root=repo.safe_path(artifacts,'public-surface')
        with repo.locked(root/'state'/f"{model['id']}.lock") as acquired:
            if not acquired:continue
            cutoff=clock().replace(second=0,microsecond=0)-timedelta(minutes=2)
            state_path=root/'state'/f"{model['id']}.json"
            try:
                state=repo.decode(repo.read(state_path,maximum=32000)) if state_path.exists() else {}
                require(isinstance(state,dict),'PUBLIC_SURFACE_STATE_INVALID')
                state=recover_previous(root,model,state)
            except (FloodModelError,OSError,ValueError,KeyError,TypeError):
                # 손상된 계보는 새 건조 시작으로 대체하지 않고 해당 유역만 중단한다.
                index_update(artifacts,model,None,models,clock())
                repo.atomic_json(root/'state'/f"{model['id']}.failure.json",
                    {'errorCode':'PUBLIC_SURFACE_STATE_RECOVERY_FAILED','at':clock().isoformat()})
                continue
            if state.get('attemptedThrough') and utc(state['attemptedThrough'])>=cutoff:continue
            identifier,token=uuid.uuid4(),uuid.uuid4()
            directory=repo.safe_path(root,f'{identifier}/{token}');directory.mkdir(parents=True)
            repo.atomic_json(state_path,state | {'status':'RUNNING','attemptedThrough':cutoff.isoformat(),
                'attemptId':str(identifier),'attemptToken':str(token)})
            worked=True
            try:
                bundle,manifest,recipe=repo.load_bundle(model)
                payload=request(recipe,cutoff)
                numerical=repo.decode(repo.read(bundle/'numerical-policy.json'))
                require(numerical.get('schemaVersion')==1
                        and is_hash(numerical.get('engineSha256'))
                        and numerical.get('modelTemplateSha256')==repo.sha(repo.encode(recipe['model'])),
                        'PUBLIC_SURFACE_NUMERICAL_POLICY_MISMATCH')
                repo.atomic_json(directory/'request.json',payload)
                snapshot(directory,bundle,manifest)
                previous=state.get('previous')
                if previous:
                    require(previous['inputBundleSha256']==model['inputBundleSha256']
                            and previous['numericalPolicySha256']==model['numericalPolicySha256'],
                            'PUBLIC_SURFACE_ORIGIN_CHANGE_REQUIRES_NEW_MODEL')
                    old=repo.safe_path(root,f"{uuid.UUID(previous['id'])}/{uuid.UUID(previous['token'])}/calculation/coupled-input.json")
                    (directory/'previous-input.json').write_bytes(repo.read(old,expected=previous['inputSha256']))
                run_engine(directory)
                row=publication(model,directory,identifier,token,cutoff,clock())
                current=repo.load_registry()
                require(current.get(model['id'])==model,'PUBLIC_SURFACE_MODEL_WITHDRAWN')
                # 게시 파일을 먼저 완성한 뒤 하나의 인덱스 교체로 독자에게 공개한다.
                files={str(p.relative_to(directory)):repo.sha(p.read_bytes()) for p in sorted(directory.rglob('*')) if p.is_file()}
                repo.atomic_json(directory/'manifest.json',{'schemaVersion':1,'files':files,
                    'previous':previous,'statePolicy':recipe['statePolicy'],'rankingEligible':False})
                row['runManifestSha256']=repo.sha(repo.read(directory/'manifest.json'))
                repo.atomic_json(directory/'publication.json',row)
                index_update(artifacts,model,row,current,clock())
                previous=row | {'inputSha256':repo.sha(repo.read(directory/'calculation/coupled-input.json'))}
                repo.atomic_json(state_path,{'status':'SUCCEEDED','attemptedThrough':cutoff.isoformat(),'previous':previous})
            except (FloodModelError,OSError,ValueError,KeyError,TypeError) as error:
                code=str(error) if isinstance(error,FloodModelError) else ''
                if not re.fullmatch('[A-Z][A-Z_0-9]{0,100}',code):code='PUBLIC_SURFACE_PRODUCTION_FAILED'
                repo.atomic_json(directory/'failure.json',{'status':'FAILED','errorCode':code,
                    'attemptedThrough':cutoff.isoformat()})
                index_update(artifacts,model,None,models,clock())
                repo.atomic_json(state_path,state | {'status':'FAILED','attemptedThrough':cutoff.isoformat(),
                    'errorCode':code})
    return worked
