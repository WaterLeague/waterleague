"""보관 14일 실제 강우·기상으로 지표 초기화 기간과 시간 간격 비교."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'simulation'))
from verify_observed_surface_rainfall import specification
from verify_surface_infiltration import soil_source
from waterleague_sim.engine.flood_errors import require
from waterleague_sim.engine.surface_infiltration import library_path
from waterleague_sim.forcing.surface_evaporation import TRANSFER
from waterleague_sim.forcing.surface_initialization import run_initialized_surface
from waterleague_sim.reference.flood_cases import mesh

REFERENCE = {'file': 'seoul-20220808-421-14d-v1.json.gz',
             'sha256': '95c290cbbaaee551c73e3f24795605945bcc4d978b2b6c225392f5aef1f7fe98'}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, allow_nan=False, indent=2)+'\n')


def inputs(soil):
    model = mesh(1, 1, 10, 10)
    rain = specification(model, minutes=359, two_stations=False)
    model.update(schemaVersion=2, startUtc=rain['startUtc'], durationSeconds=359*60,
                 evidence='OBSERVED_ANTECEDENT_ON_SYNTHETIC_DOMAIN_NOT_SEOUL')
    model['infiltration'] = {'schemaVersion': 1, 'method': 'GREEN_AMPT', 'ownershipPolicy': 'SURFACE_ONLY',
        'initialization': 'EPA_INITIAL_DEFICIT_SEED', 'recoveryFactor': 1., 'imperviousTriangles': [],
        'evidence': {'soil': soil, 'seed': '선행 이전 최대 수분 부족 0.25의 명시적 시드; 현장 관측 아님'},
        'regions': [{'triangles': [0, 1], 'perviousFraction': 1., 'suctionMm': soil['suctionMm'],
            'conductivityMmH': soil['conductivityRangeMmH'][0], 'initialMoistureDeficit': .25,
            'evidence': {'parameters': soil, 'area': '합성 평탄 전면 투수 100m²'}}]}
    file = 'seoul-20220808-fao56-v1.json'
    model['evaporation'] = {'schemaVersion': 1, 'type': 'ARCHIVED_FAO56', 'ownershipPolicy': 'SURFACE_ONLY',
        'surfaceTransfer': TRANSFER, 'reference': {'file': file, 'sha256': sha(ROOT/'data/derived/evaporation'/file)},
        'evidence': '서울 108 관측 기반 기준 증발산의 지표수 전용; 표면별 보정 미수행'}
    initialization = {'schemaVersion': 1, 'method': 'OBSERVED_ANTECEDENT_CONTINUOUS_V1', 'days': 14,
        'stations': [REFERENCE], 'weatherReference': REFERENCE,
        'evidence': '실제 성동 421 선행 강우와 서울 108 기상; 합성 격자의 기간 민감도 진단'}
    return model, rain, initialization


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    directory = args.output.resolve()
    require(not directory.exists(), 'SURFACE_INITIALIZATION_OUTPUT_EXISTS')
    directory.mkdir(parents=True)
    soil = soil_source(directory / 'public-soil')
    base, rain, initialization = inputs(soil)
    cases, results, states = [], {}, {}
    for name, days, step in [('7d-60s', 7, 60.), ('14d-60s', 14, 60.),
                              ('14d-30s', 14, 30.), ('replay-14d-60s', 14, 60.)]:
        model = deepcopy(base)
        model['maxStepSeconds'] = step
        result = run_initialized_surface(model, rain, initialization | {'days': days}, directory/name)
        results[name] = result
        state = json.loads((directory/name/'evaluation-initial-state.json').read_bytes())
        states[name] = state
        case = {'name': name, 'warmupDays': days, 'maximumStepSeconds': step,
            'status': result['numericalStatus'], 'evaluation': result['initialization']['evaluationLedger'],
            'evaluationInitialState': state, 'rainfall': result['observedRainfall'],
            'quality': result['numericalQuality'],
            'resultSha256': sha(directory/name/'observed-surface-result.json')}
        cases.append(case)
        print(name, case['status'], json.dumps(case['evaluation']), flush=True)
    a, b, short = (results[name]['initialization']['evaluationLedger'] for name in ('14d-60s', '14d-30s', '7d-60s'))
    comparison = {'sameMaterialAndSeedAcrossDurations': True,
        'exactReplay': results['14d-60s']['final'] == results['replay-14d-60s']['final']
            and states['14d-60s'] == states['replay-14d-60s'],
        'period14Minus7': {k: a[k]-short[k] for k in ('initialStorageM3', 'infiltrationM3', 'surfaceEvaporationM3', 'finalStorageM3')},
        'step60Minus30': {k: a[k]-b[k] for k in ('initialStorageM3', 'infiltrationM3', 'surfaceEvaporationM3', 'finalStorageM3')},
        'initialNativeState14Minus7': [[x-y for x,y in zip(long,short)] for long,short in
            zip(states['14d-60s']['infiltration']['nativeState'], states['7d-60s']['infiltration']['nativeState'])]}
    sources = [Path(__file__), ROOT/'scripts/verify_surface_infiltration.py',
        ROOT/'scripts/verify_observed_surface_rainfall.py', ROOT/'scripts/prepare_site_physics.py',
        ROOT/'scripts/build_surface_infiltration.py', ROOT/'simulation/native/surface_infiltration.inc',
        ROOT/'simulation/uv.lock', ROOT/'data/manifests/anuga-4.0.1.json']
    for folder in ('engine', 'forcing', 'ingestion', 'reference'):
        sources.extend(sorted((ROOT/'simulation/waterleague_sim'/folder).glob('*.py')))
    for source in sources:
        target = directory/'source'/source.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    native = directory/'native'
    native.mkdir()
    for source in (library_path(), library_path().parent/'soil-build.json', ROOT/'tmp/swmm/source.tar.gz'):
        shutil.copyfile(source, native/source.name)
    report = {'schemaVersion': 1, 'classification': base['evidence'], 'rankingEligible': False,
        'cases': cases, 'comparison': comparison, 'soil': soil,
        'sourceCode': {str(p.relative_to(ROOT)): sha(p) for p in sources},
        'limitations': ['합성 평탄 격자·전면 투수·차단 경계; 실제 서울 유역 재현 아님',
            '최대 수분 부족 매개변수 0.25·회복계수 1의 시드/모형 가정 유지',
            '기간 비교는 같은 시드·재료 조건; 별도 건습 상태 민감도 미완료',
            'EPA 경험식 회복·지표수 제한 증발이며 토양/뿌리/지하수 전체 수지 아님',
            '선행 구간의 관측 총량 평균·품질 경고 보존; 평가 구간 품질 완화 없음']}
    write(directory/'summary.json', report)
    files = {str(p.relative_to(directory)): sha(p) for p in sorted(directory.rglob('*')) if p.is_file()}
    write(directory/'artifact-manifest.json', {'schemaVersion': 1, 'files': files})
    require(comparison['exactReplay'] and all(c['status'] == 'PASSED' for c in cases),
            'SURFACE_INITIALIZATION_DIAGNOSTIC_FAILED')
    print(json.dumps({'files': len(files), 'manifestSha256': sha(directory/'artifact-manifest.json'),
                      'comparison': comparison}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
