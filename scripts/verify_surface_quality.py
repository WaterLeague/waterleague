"""고정 공식 소스·실제 강우·해석 사례로 지표 수치 정책 비교 및 보존."""
import argparse
import json
from pathlib import Path
import platform
import shutil
import sys
import tarfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'simulation'))

from verify_observed_surface_rainfall import specification, digest
from waterleague_sim.engine.coupled_flood import run_coupled
from waterleague_sim.engine.flood_errors import FloodModelError, require
from waterleague_sim.engine.flood_process import EngineProcess
from waterleague_sim.forcing.surface_run import run_observed_surface
from waterleague_sim.reference.flood_cases import mesh, coupled_case


def official_sources(directory):
    manifest = json.loads((ROOT / 'data/manifests/anuga-4.0.1.json').read_bytes())
    archive = ROOT / manifest['source']['path']
    require(digest(archive) == manifest['source']['sha256'], 'SURFACE_SOURCE_HASH_MISMATCH')
    members = ['anuga/abstract_2d_finite_volumes/general_mesh.py',
               'anuga/shallow_water/gpu/core_kernels.c', 'anuga/shallow_water/sw_domain_openmp.c']
    with tarfile.open(archive) as bundle:
        for name in members:
            target = directory / 'official-source' / name
            target.parent.mkdir(parents=True, exist_ok=True)
            with bundle.extractfile('anuga-4.0.1/' + name) as stream:
                target.write_bytes(stream.read())
    return {'sourceArchiveSha256': manifest['source']['sha256'],
            'releaseUrl': manifest['releaseUrl'], 'files': {
                name: digest(directory / 'official-source' / name) for name in members}}


def analytical_cases(directory):
    import numpy as np
    results = []
    lake = mesh(bed=lambda x, y: .3 * np.sin(x / 20 * np.pi), water=lambda x, z: 1 - z)
    lake['schemaVersion'] = 2
    with EngineProcess('surface', lake, directory / 'lake') as session:
        state = session.call('advance', 30)
        result = session.call('finish')
    maximum_velocity = max(abs(v) for v in state['velocityXMps'] + state['velocityYMps'])
    error = max(abs(a-b) for a, b in zip(state['depthM'], lake['initialDepthM']))
    require(maximum_velocity < 1e-9 and error < 1e-10, 'SURFACE_LAKE_COMPARISON_FAILED')
    results.append({'case': 'NONFLAT_LAKE_AT_REST', 'maximumVelocityMps': maximum_velocity,
                    'maximumDepthErrorM': error, 'quality': result['numericalQuality']})
    errors = []
    for nx in (100, 200):
        model = mesh(nx, 5, 200, 10, water=lambda x, z: (x < 100).astype(float))
        model['schemaVersion'] = 2
        with EngineProcess('surface', model, directory / f'dry-dam-{nx}') as session:
            state = session.call('advance', 5)
            gravity = session.info['gravityMps2']
            result = session.call('finish')
        points, triangles = np.asarray(model['verticesM']), np.asarray(model['triangles'])
        x = points[triangles, 0].mean(axis=1) - 100
        c = np.sqrt(gravity)
        exact = np.where(x < -5*c, 1, np.where(x > 10*c, 0, (2*c - x/5)**2 / (9*gravity)))
        error = float(np.mean(abs(np.asarray(state['depthM']) - exact)))
        errors.append(error)
        require(result['numericalStatus'] == 'PASSED', 'SURFACE_DAM_BALANCE_FAILED')
        results.append({'case': 'DRY_DAM_BREAK_RITTER', 'nx': nx, 'meanAbsoluteDepthErrorM': error,
                        'quality': result['numericalQuality']})
    require(errors[1] < errors[0] and errors[1] < .01, 'SURFACE_DAM_REFINEMENT_FAILED')
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    directory = args.output.resolve()
    require(not directory.exists(), 'SURFACE_QUALITY_OUTPUT_EXISTS')
    directory.mkdir(parents=True)
    sources = [Path(__file__), ROOT / 'scripts/verify_observed_surface_rainfall.py',
               ROOT / 'simulation/uv.lock', ROOT / 'simulation/pyproject.toml',
               ROOT / 'data/manifests/anuga-4.0.1.json']
    for folder in ('forcing', 'ingestion', 'engine', 'reference', 'evaluation'):
        sources.extend(sorted((ROOT / 'simulation/waterleague_sim' / folder).glob('*.py')))
    for source in sources:
        target = directory / 'source' / source.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    report = {'schemaVersion': 1, 'classification': 'OBSERVED_RAIN_ON_SYNTHETIC_HYDRAULICS',
              'rankingEligible': False, 'officialSource': official_sources(directory),
              'runtime': {'platform': platform.platform(), 'python': platform.python_version(),
                          'timingScope': '단일 호스트 순차 실행; 프로세스 기동·관측 검증·파일 저장 포함'},
              'sourceCode': {str(source.relative_to(ROOT)): digest(source) for source in sources},
              'cases': []}
    results = {}
    for name, version, step in [('legacy-30s', 1, 30.), ('legacy-1s', 1, 1.),
                                ('incircle-30s', 2, 30.), ('incircle-1s', 2, 1.),
                                ('incircle-01s', 2, .1), ('incircle-005s', 2, .05),
                                ('replay-30s', 2, 30.)]:
        model = mesh(2, 2) | {'schemaVersion': version, 'maxStepSeconds': step}
        path = directory / name
        started = time.perf_counter()
        row = {'name': name, 'inputVersion': version, 'maximumStepSeconds': step}
        try:
            result = run_observed_surface(model, specification(model), path)
            results[name] = result
            row.update(status=result['numericalStatus'], final=result['final'],
                quality=result['numericalQuality'], rainfall=result['observedRainfall'],
                resultSha256=digest(path / 'observed-surface-result.json'))
        except FloodModelError as error:
            failure = json.loads((path / 'observed-surface-failure.json').read_bytes())
            row.update(status='FAILED', code=str(error), lastSurface=failure['lastSurface'],
                       failureSha256=digest(path / 'observed-surface-failure.json'))
        row['wallTimeSeconds'] = time.perf_counter() - started
        row['numericalConfiguration'] = json.loads((path / 'surface/surface-numerics.json').read_bytes())
        require(row['status'] == ('FAILED' if version == 1 else 'PASSED'),
                'SURFACE_QUALITY_UNEXPECTED_STATUS')
        report['cases'].append(row)
        print(name, row['status'], round(row['wallTimeSeconds'], 3), flush=True)
    a, b = results['incircle-30s'], results['replay-30s']
    require(a['final'] == b['final'] and a['numericalQuality'] == b['numericalQuality'],
            'SURFACE_QUALITY_REPLAY_MISMATCH')
    report['timeComparison'] = {'exactReplay': True, 'referenceMaximumStepSeconds': .05,
        'comparisons': [{'maximumStepSeconds': step,
            'maximumDepthDifferenceM': max(abs(x-y) for x, y in
                zip(results[name]['final']['depthM'], results['incircle-005s']['final']['depthM'])),
            'storageDifferenceM3': results[name]['final']['storageM3']
                - results['incircle-005s']['final']['storageM3']}
            for name, step in [('incircle-30s', 30.), ('incircle-1s', 1.), ('incircle-01s', .1)]]}
    report['analyticalCases'] = analytical_cases(directory)
    print('analytical cases PASSED', flush=True)
    model = coupled_case(initial_network=0, exchange_ms=500)
    model['surface']['schemaVersion'] = 2
    model['network']['inputText'] = model['network']['inputText'].replace('01/01/2020', '08/08/2022')
    model['network']['inputText'] = model['network']['inputText'].replace('00:00:00', '09:00:00')
    model['network']['inputText'] = model['network']['inputText'].replace('00:02:01', '09:02:01')
    model['network']['timeZone'] = 'UTC'
    model['observedRainfall'] = specification(model['surface'], minutes=2, two_stations=False)
    result = run_coupled(model, directory / 'coupled')
    require(result['numericalStatus'] == 'PASSED', 'SURFACE_QUALITY_COUPLED_FAILED')
    report['coupled'] = {key: result[key] for key in ('numericalStatus', 'balance', 'observedRainfall',
                                                    'surfaceNumericalQuality')}
    report['limitations'] = ['실제 359분 강우의 합성 평탄 격자 배정; 실제 서울 지형·관망·침수 재현 아님',
        '명시한 공식 반경 옵션과 입력 버전 변경; 기존 실패·원본 보존, 설치된 엔진 수정 없음',
        '같은 입력의 시간 간격·해석 사례 비교이며 모든 격자/경계의 수치 안정성 보증 아님',
        '수지 통과와 수심/유속 수렴은 별도 판정; 큰 최대 간격의 실행 속도로 운영 설정 선정 금지',
        '지표 침투·증발산·현장 선행 수분·실제 연결 시설과 독립 관측 대조는 별도 잔여 범위']
    report['files'] = {str(p.relative_to(directory)): digest(p)
                       for p in sorted(directory.rglob('*')) if p.is_file()}
    (directory / 'manifest.json').write_text(json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2) + '\n')
    print(json.dumps(report['timeComparison'], ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
