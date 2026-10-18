"""보관 28일 관측과 동일 연결 유역의 시설 시드·기간·간격 비교."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import platform
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'simulation'))

from waterleague_sim.engine.coupled_flood import run_coupled
from waterleague_sim.engine.connected_facilities import compile_design
from waterleague_sim.engine.coupled_facility_network import library_path as network_library
from waterleague_sim.engine.surface_infiltration import library_path as soil_library
from waterleague_sim.engine.flood_errors import FloodModelError, require
from waterleague_sim.evaluation.coupled_adapter import file_digest
from waterleague_sim.evaluation.coupled_initialization_study import SEEDED_TYPES, fixed_input, summarize_case, difference
from waterleague_sim.evaluation.exception import EvaluationError
from waterleague_sim.evaluation.values import digest
from waterleague_sim.reference.initialized_coupling import inputs

REFERENCE = {'file': 'seoul-20220808-421-28d-v1.json.gz',
             'sha256': '113dc1376856067904f1fe5ea5619105bb05b5160a042f50375955918e2c3f53'}


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2)+'\n')


def specifications():
    design = json.loads((ROOT/'simulation/tests/fixtures/connected-facilities-v1.json').read_bytes())
    cases = [(f'{days}d-{seed}pct-60s', days, seed, 60) for days in (7, 14, 28) for seed in (0, 100)]
    cases += [('28d-0pct-30s', 28, 0, 30), ('replay-28d-0pct-60s', 28, 0, 60)]
    models = {}
    for name, days, seed, step in cases:
        variant = deepcopy(design)
        for row in variant['placements']:
            row['initialSaturationPercent'] = seed if row['facilityType'] in SEEDED_TYPES else 0
        models[name] = inputs(variant, days=days, step=step, antecedent_reference=REFERENCE)
        compile_design(models[name]['network']['inputText'].encode(), variant)
    require(len({digest(fixed_input(model)) for model in models.values()}) == 1,
            'INITIALIZATION_STUDY_INPUT_MISMATCH')
    return models


def archive_source(directory):
    paths = list((ROOT/'simulation/waterleague_sim').rglob('*.py'))
    paths += list((ROOT/'simulation/native').glob('*.inc')) + list((ROOT/'scripts').glob('*.py'))
    paths += list((ROOT/'backend/src/main/resources/facilities').glob('*.json'))
    paths += [ROOT/p for p in ('simulation/tests/fixtures/connected-facilities-v1.json',
        'simulation/pyproject.toml', 'simulation/uv.lock', 'scripts/build_swmm.sh',
        'data/manifests/anuga-4.0.1.json', 'tmp/swmm/source.tar.gz')]
    for binary in (network_library(), soil_library()):
        paths.append(binary)
        paths += list(binary.parent.glob('*build.json'))
    for path in paths:
        target = directory/'source'/path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    return {str(path.relative_to(ROOT)): file_digest(path) for path in paths}


def comparisons(cases):
    result = {}
    def add(name, left, right, variable):
        a, b = cases[left], cases[right]
        if 'fixedInputSha256' not in a or 'fixedInputSha256' not in b:
            result[name] = {'status': 'WITHHELD', 'difference': None, 'reason': 'EXECUTION_FAILED'}
        else:
            result[name] = difference(a, b, variable=variable)
    for days in (7, 14, 28):
        add(f'{days}d-wet-minus-dry', f'{days}d-100pct-60s', f'{days}d-0pct-60s', 'initialSaturationPercent')
    for seed in (0, 100):
        for days, previous in ((14, 7), (28, 14)):
            add(f'{days}d-minus-{previous}d-{seed}pct', f'{days}d-{seed}pct-60s',
                f'{previous}d-{seed}pct-60s', 'warmupDays')
    add('28d-60s-minus-30s', '28d-0pct-60s', '28d-0pct-30s', 'maximumExchangeMilliseconds')
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    directory = args.output.resolve()
    require(not directory.exists(), 'INITIALIZATION_STUDY_OUTPUT_EXISTS')
    models = specifications()
    directory.mkdir(parents=True)
    report = {'schemaVersion': 1, 'classification': 'OBSERVED_FORCING_SYNTHETIC_CONNECTED_DOMAIN',
        'rankingEligible': False, 'antecedentReference': REFERENCE, 'cases': {},
        'sourceCode': archive_source(directory),
        'runtime': {'python': platform.python_version(), 'system': platform.system(), 'machine': platform.machine()},
        'limitations': ['실제 강우·기상과 합성 지형/관망의 수치 진단; 서울 현장 침수 재현 아님',
            '생물저류/침투 트렌치/빗물이용조 InitSat만 변경; 식생수로와 관망/지표 수량·토양 시드는 고정',
            '시설 단면·원지반 침투·경사·조도·강우 공간 배정의 문헌값/설계 가정 유지',
            '선행 총량 평균 배분·품질 경고 유지; 평가 관측 판정 완화 없음',
            '고정한 합성 경계에서의 비교; 공개 관망 외부 유입·경계를 날짜 이동한 결과 아님',
            '보편 수렴 인증·운영 초기화 정책 변경·경쟁 순위 발행 없음']}
    write(directory/'study-inputs.json', models)
    try:
        for name, model in models.items():
            print('START', name, flush=True)
            try:
                run_coupled(model, directory/name)
                report['cases'][name] = summarize_case(directory/name)
            except Exception as error:
                report['cases'][name] = {'status': 'FAILED', 'complete': False,
                    'code': str(error) if isinstance(error, (FloodModelError, EvaluationError)) else type(error).__name__}
            write(directory/'summary.json', report)
            print('FINISH', name, report['cases'][name]['status'], flush=True)
        report['comparisons'] = comparisons(report['cases'])
        a, b = directory/'28d-0pct-60s', directory/'replay-28d-0pct-60s'
        names = ('evaluation-initial-state.json', 'evaluation-final-state.json', 'network/network.out')
        report['exactReplay'] = all((a/name).is_file() and (b/name).is_file()
            and file_digest(a/name) == file_digest(b/name) for name in names)
        report['status'] = 'PASSED' if report['exactReplay'] and all(
            row['status'] == 'PASSED' and row['complete'] for row in report['cases'].values()) else 'FAILED'
    finally:
        write(directory/'summary.json', report)
        files = {str(p.relative_to(directory)): file_digest(p) for p in sorted(directory.rglob('*')) if p.is_file()}
        write(directory/'manifest.json', {'schemaVersion': 1, 'files': files})
    print(json.dumps({'status': report['status'], 'files': len(files),
        'manifestSha256': file_digest(directory/'manifest.json')}, ensure_ascii=False), flush=True)
    require(report['status'] == 'PASSED', 'INITIALIZATION_STUDY_FAILED')


if __name__ == '__main__':
    main()
