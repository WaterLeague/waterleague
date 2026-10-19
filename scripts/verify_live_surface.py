"""최신 직접 응답과 보관 호우의 실제 엔진 실행·동일 입력 재현 근거 보존."""
import argparse
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'simulation'))
from run_live_surface import execute
from waterleague_sim.engine.flood_errors import require
from waterleague_sim.engine.coupled_flood import run_coupled
from waterleague_sim.forcing.live_rainfall import METHOD
from waterleague_sim.forcing.surface_run import run_observed_surface
from waterleague_sim.reference.flood_cases import mesh


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2)+'\n')


def domain(start, duration):
    model = mesh(4, 4, 20, 20)
    model.update(schemaVersion=2, startUtc=start.isoformat(), durationSeconds=duration,
        maxStepSeconds=.1, evidence='DIRECT_OFFICIAL_RAIN_SYNTHETIC_CLOSED_TANK_NOT_SEOUL',
        frameOutput={'schemaVersion':1, 'type':'NATIVE_CENTROID_FLOAT64',
                     'maxFrames':5000, 'maxBytes':32*1024**2})
    return model


def compare_frames(first, second):
    result = {}
    for file in sorted((first/'surface/native-frames').glob('*')):
        expected, actual = sha(file), sha(second/'surface/native-frames'/file.name)
        require(expected == actual, 'LIVE_SURFACE_REPLAY_MISMATCH')
        result[file.name] = expected
    return result


def main():
    from local_config import load
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    out = args.output.resolve()
    require(not out.exists(), 'LIVE_SURFACE_VERIFICATION_OUTPUT_EXISTS')
    load(); os.umask(0o077)
    end = datetime.now(timezone.utc).replace(second=0, microsecond=0)-timedelta(minutes=2)
    start = end-timedelta(minutes=10)
    model = domain(start, 600)
    request = {'mode':'surface', 'model':model, 'rainfall':{
        'startUtc':start.isoformat(), 'endUtc':end.isoformat(),
        'stationByTriangle':['421' if i%2 else '401' for i in range(len(model['triangles']))],
        'assignmentEvidence':'최신 API의 합성 수조 격자 교차 배정 검사; 서울 유역·관측 공간 대표성 근거 아님'}}
    # 실행 전에 원본 코드를 별도 보존하며 출력 폴더 재사용으로 이전 증거를 덮어쓰지 않는다.
    out.mkdir(parents=True)
    sources = [Path(__file__), ROOT/'scripts/run_live_surface.py', ROOT/'simulation/uv.lock',
        ROOT/'simulation/pyproject.toml', ROOT/'data/manifests/anuga-4.0.1.json']
    for folder in ('engine', 'forcing', 'ingestion', 'reference'):
        sources += sorted((ROOT/'simulation/waterleague_sim'/folder).glob('*.py'))
    for source in sources:
        target = out/'source'/source.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(source, target)
    write(out/'live-request.json', request)
    live_result = execute(request, out/'latest', os.environ.get('KMA_API_KEY', ''))
    saved = json.loads((out/'latest/observed-surface-input.json').read_bytes())
    # 재생은 직접 조회 함수를 거치지 않으며 보관된 원 응답에서만 강우를 재산정한다.
    replay = run_observed_surface(saved['surface'], saved['observedRainfall'], out/'latest-replay')
    require(live_result['final'] == replay['final'], 'LIVE_SURFACE_REPLAY_MISMATCH')
    replay_files = compare_frames(out/'latest', out/'latest-replay')
    print('latest', live_result['numericalStatus'], flush=True)

    past_start = datetime(2022, 8, 8, 10, 1, tzinfo=timezone.utc)
    past_end = datetime(2022, 8, 8, 14, 59, tzinfo=timezone.utc)
    past_model = domain(past_start, int((past_end-past_start).total_seconds()))
    direct = {'schemaVersion':2, 'sourceType':METHOD, 'startUtc':past_start.isoformat(),
        'endUtc':past_end.isoformat(), 'stationByTriangle':saved['observedRainfall']['stationByTriangle'],
        'assignmentEvidence':'이미 확보한 공식 호우 원문 형식 호환 검사; 최신 조회·서울 유역 아님', 'stations':[]}
    legacy = {k:v for k,v in direct.items() if k!='sourceType'} | {'schemaVersion':1, 'stations':[]}
    for station in ('401','421'):
        name = f'kma-{station}-202208081800-202208082359'
        original_manifest = ROOT/'data/manifests'/f'{name}.json'
        meta = json.loads(original_manifest.read_bytes())
        raw_path = ROOT/'data/raw'/f'{name}.txt'
        raw = raw_path.read_bytes()
        require(sha(raw_path) == meta['sha256'], 'LIVE_SURFACE_SOURCE_CHANGED')
        metadata = {'provider':'KMA_AWS_DIRECT', 'endpoint':meta['endpoint'], 'parameters':meta['parameters'],
            'fetchedAt':meta['acquiredAt'], 'sha256':meta['sha256'], 'purpose':'SIMULATION_USED_INPUT_ONLY'}
        direct['stations'].append({'stationId':station, 'responses':[{'rawUtf8':raw.decode(), 'metadata':metadata}]})
        reference = ROOT/'data/derived/rainfall'/f'{name}-disaster-v1.json'
        legacy['stations'].append({'file':reference.name, 'sha256':sha(reference)})
        for source in (original_manifest, raw_path, reference):
            target=out/'original-past'/source.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(source, target)
    a = run_observed_surface(past_model, direct, out/'past-direct-format')
    b = run_observed_surface(past_model, legacy, out/'past-legacy-format')
    require(a['final'] == b['final'], 'LIVE_SURFACE_LEGACY_PHYSICS_CHANGED')
    legacy_files = compare_frames(out/'past-direct-format', out/'past-legacy-format')
    print('past', a['numericalStatus'], flush=True)
    report = {'schemaVersion':1, 'classification':'DIRECT_FORCING_ENGINE_DIAGNOSTIC_NOT_SEOUL',
        'rankingEligible':False, 'publiclyPublished':False,
        'latest':{k:live_result[k] for k in ('numericalStatus','observedRainfall','final','numericalQuality')},
        'latestFramesMatched':replay_files,
        'past':{k:a[k] for k in ('numericalStatus','observedRainfall','final','numericalQuality')},
        'pastLegacyFramesMatched':legacy_files,
        'limitations':['최신 분 강우를 합성 폐쇄 수조에 적용한 입력·수지 검사',
            '초기 건조 시드이며 실제 서울 지형·배수·선행 수분·현장 검증 아님',
            '관망 소유 집수 강우의 같은 응답 결속·실시간 증발/바람/경계·공개 게시 워커 미완료',
            '기관 리그·별도 강우 화면·운영 순위 변경 없음'],
        'files':{str(p.relative_to(out)):sha(p) for p in sorted(out.rglob('*')) if p.is_file()}}
    write(out/'manifest.json', report)
    print(json.dumps({'latestRainM3':report['latest']['observedRainfall']['expectedSurfaceRainfallM3'],
        'pastRainM3':report['past']['observedRainfall']['expectedSurfaceRainfallM3'],
        'liveFilesMatched':len(replay_files), 'legacyFilesMatched':len(legacy_files)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
