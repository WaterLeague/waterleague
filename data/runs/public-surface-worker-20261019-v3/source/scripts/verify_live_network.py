"""공식 응답의 관망·지표 중복 없는 투입과 네이티브 재현 근거 보존."""
import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'simulation'))
from run_live_surface import execute
from waterleague_sim.engine.coupled_flood import run_coupled
from waterleague_sim.engine.flood_errors import require
from waterleague_sim.evaluation.coupled_adapter import engine_signature, file_digest, read_coupled_record
from waterleague_sim.forcing.live_rainfall import METHOD
from waterleague_sim.reference.coupled_facilities import coupled_facility_case


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2)+'\n')


def domain(start, end):
    model = coupled_facility_case(None)
    duration = int((end-start).total_seconds())
    model.update(durationSeconds=duration, maximumExchangeMilliseconds=500, frameIntervalMilliseconds=60000)
    model['surface'].update(schemaVersion=2, startUtc=start.isoformat(),
        frameOutput={'schemaVersion':1, 'type':'NATIVE_CENTROID_FLOAT64',
                     'maxFrames':1000, 'maxBytes':16*1024**2})
    model['evaluationMetrics']['endMilliseconds'] = duration*1000
    text = model['network']['inputText']
    for key, value in {'START_DATE':f'{start:%m/%d/%Y}', 'START_TIME':f'{start:%H:%M:%S}',
                      'REPORT_START_DATE':f'{start:%m/%d/%Y}', 'REPORT_START_TIME':f'{start:%H:%M:%S}',
                      'END_DATE':f'{end+timedelta(seconds=1):%m/%d/%Y}',
                      'END_TIME':f'{end+timedelta(seconds=1):%H:%M:%S}'}.items():
        text = '\n'.join(key+' '+value if line.startswith(key+' ') else line for line in text.splitlines())+'\n'
    model['network'].update(inputText=text, timeZone='UTC')
    return model


def compared(first, second):
    names = ['rainfall-network.inp', 'network/network.inp', 'network/network.out', 'network-frames.jsonl']
    names += [str(p.relative_to(first)) for p in (first/'surface/native-frames').glob('*') if p.is_file()]
    names += [p.name for p in first.glob('*ledger*') if p.is_file()]
    result = {}
    for name in names:
        require(file_digest(first/name) == file_digest(second/name), 'LIVE_NETWORK_REPLAY_MISMATCH')
        result[name] = file_digest(first/name)
    return result


def snapshot_source(out):
    sources = [Path(__file__), ROOT/'scripts/run_live_surface.py', ROOT/'scripts/build_rainfall_swmm.py',
        ROOT/'scripts/build_live_swmm.py', ROOT/'simulation/uv.lock', ROOT/'simulation/pyproject.toml',
        ROOT/'data/manifests/anuga-4.0.1.json']
    sources += list((ROOT/'simulation/waterleague_sim').rglob('*.py'))
    sources += list((ROOT/'simulation/native').glob('*.inc'))
    sources += list((ROOT/'tmp/network-rainfall-swmm-build/install/bin').glob('*'))
    for source in sources:
        if source.is_file():
            target = out/'source'/source.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source,target)


def main():
    from local_config import load
    parser = argparse.ArgumentParser()
    parser.add_argument('--output',required=True,type=Path)
    args = parser.parse_args()
    out = args.output.resolve()
    require(not out.exists(),'LIVE_NETWORK_OUTPUT_EXISTS')
    load(); os.umask(0o077)
    out.mkdir(parents=True); snapshot_source(out)
    end = datetime.now(timezone.utc).replace(second=0,microsecond=0)-timedelta(minutes=2)
    start = end-timedelta(minutes=5)
    model = domain(start,end)
    request = {'mode':'coupled', 'model':model, 'rainfall':{
        'startUtc':start.isoformat(), 'endUtc':end.isoformat(),
        'stationByTriangle':['421' if o=='SURFACE' else None for o in model['surface']['rainfallOwner']],
        'stationByCatchment':{'S1':'401'},
        'assignmentEvidence':'합성 100m² 집수+100m² 직접 강우 구분; 실제 서울 유역 배정 아님'}}
    write(out/'live-request.json',request)
    latest = execute(request,out/'latest',os.environ.get('KMA_API_KEY',''))
    print('latest',latest['numericalStatus'],flush=True)
    saved = json.loads((out/'latest/coupled-input.json').read_bytes())
    replay = run_coupled(saved,out/'latest-replay')
    require(latest['balance'] == replay['balance'] and latest['networkRainfall'] == replay['networkRainfall'],
            'LIVE_NETWORK_REPLAY_MISMATCH')
    latest_matches = compared(out/'latest',out/'latest-replay')
    start, end = datetime(2022,8,8,10,1,tzinfo=timezone.utc),datetime(2022,8,8,14,59,tzinfo=timezone.utc)
    past_model = domain(start,end)
    specification = {k:v for k,v in request['rainfall'].items()} | {'schemaVersion':2, 'sourceType':METHOD,
        'startUtc':start.isoformat(), 'endUtc':end.isoformat(), 'stations':[],
        'assignmentEvidence':'보관 공식 호우의 합성 영역 배정; 당시 서울 침수 복원 아님'}
    for station in ('401','421'):
        stem = f'kma-{station}-202208081800-202208082359'
        manifest = ROOT/'data/manifests'/f'{stem}.json'
        raw = ROOT/'data/raw'/f'{stem}.txt'
        meta = json.loads(manifest.read_bytes())
        require(file_digest(raw) == meta['sha256'],'LIVE_NETWORK_SOURCE_CHANGED')
        metadata = {'provider':'KMA_AWS_DIRECT', 'endpoint':meta['endpoint'], 'parameters':meta['parameters'],
            'fetchedAt':meta['acquiredAt'], 'sha256':meta['sha256'], 'purpose':'SIMULATION_USED_INPUT_ONLY'}
        specification['stations'].append({'stationId':station,'responses':[{'rawUtf8':raw.read_text(),'metadata':metadata}]})
        for path in (manifest,raw):
            target=out/'original-past'/path.relative_to(ROOT)
            target.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(path,target)
    past_model['observedRainfall'] = specification
    past = run_coupled(past_model,out/'past')
    print('past',past['numericalStatus'],flush=True)
    report = {'schemaVersion':1,'classification':'NUMERICAL_DIRECT_FORCING_NOT_SEOUL',
        'rankingEligible':False,'publiclyPublished':False,
        'latest':{k:latest[k] for k in ('numericalStatus','networkRainfall','observedRainfall','balance')},
        'latestMatchedFiles':latest_matches,
        'past':{k:past[k] for k in ('numericalStatus','networkRainfall','observedRainfall','balance')},
        'limitations':['명시적 합성 지형·관망, 현장 유역 검증 아님',
            '직접 강우 면적과 관망 집수 면적 분리; 토양·관망·지표 전체 수지와 구분',
            '실제 선행 상태·현재 증발/풍응력·자산/시설 조합·자동 지도 게시 미완료'],
        'files':{str(p.relative_to(out)):file_digest(p) for p in sorted(out.rglob('*')) if p.is_file()}}
    write(out/'manifest.json',report)
    print(json.dumps({'latestM3':latest['networkRainfall']['appliedCombinedRainfallM3'],
        'pastM3':past['networkRainfall']['appliedCombinedRainfallM3'],
        'pastNativeResidualM3':past['networkRainfall']['nativeVolumeResidualM3'],
        'pastSurfaceResidualM3':past['observedRainfall']['volumeResidualM3']},ensure_ascii=False))


if __name__=='__main__':
    main()
