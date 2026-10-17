"""공개 DEM의 실제 강우 연결·시간 간격·명시적 외곽 경계 비교."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'simulation'))

from prepare_ngii_surface import prepare, sha, write
from verify_observed_surface_rainfall import specification
from waterleague_sim.engine.flood_errors import FloodModelError, require
from waterleague_sim.forcing.surface_run import run_observed_surface


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    directory = args.output.resolve()
    require(not directory.exists(), 'TERRAIN_OUTPUT_EXISTS')
    directory.mkdir(parents=True)
    terrain, source = prepare(directory / 'terrain')
    sources = [Path(__file__), ROOT / 'scripts/prepare_ngii_surface.py',
               ROOT / 'scripts/verify_observed_surface_rainfall.py']
    for folder in ('engine', 'forcing', 'ingestion', 'terrain'):
        sources.extend(sorted((ROOT / 'simulation/waterleague_sim' / folder).glob('*.py')))
    for path in sources:
        target = directory / 'source' / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    report = {'schemaVersion': 1, 'classification': 'PUBLIC_DEM_REFERENCE_UNVERIFIED_DIAGNOSTIC',
        'rankingEligible': False, 'surfaceInputManifestSha256': sha(directory / 'terrain/terrain-input-manifest.json'),
        'terrain': {key: source[key] for key in ('vertices', 'triangles', 'areaM2', 'heightRangeRaw',
                                                'sourceArchiveSha256', 'verticalReference')},
        'cases': [], 'sourceCode': {str(path.relative_to(ROOT)): sha(path) for path in sources}}
    results = {}
    for name, step, boundary in [('open-01s', .1, 'TRANSMISSIVE'), ('open-005s', .05, 'TRANSMISSIVE'),
                                 ('replay-01s', .1, 'TRANSMISSIVE'), ('closed-01s', .1, 'REFLECTIVE')]:
        model = deepcopy(terrain)
        model['maxStepSeconds'] = step
        model['boundaryConditions'] = {key: {'type': boundary} for key in model['boundaryConditions']}
        model['terrainProvenance']['fieldEvidence']['boundary'] = (
            '사각 창의 전달 경계 시험; 실제 외부 수위·유입·배수 경계 미확인' if boundary == 'TRANSMISSIVE'
            else '사각 창의 차단 경계 민감도 시험; 실제 벽·분수계 아님')
        rain = specification(model, minutes=60, two_stations=False)
        rain['assignmentEvidence'] = '성동 421의 실제 60분 관측을 성수 주변 DEM 창에 동일 적용; 면적 강우 실측 아님'
        path = directory / name
        row = {'name': name, 'maximumStepSeconds': step, 'boundaryType': boundary}
        try:
            result = run_observed_surface(model, rain, path)
            results[name] = result
            final = result['final']
            row.update(status=result['numericalStatus'],
                final={key: value for key, value in final.items() if key not in ('depthM', 'velocityXMps', 'velocityYMps')},
                maximumDepthM=max(final['depthM']),
                maximumSpeedMps=max((x*x+y*y)**.5 for x, y in zip(final['velocityXMps'], final['velocityYMps'])),
                quality=result['numericalQuality'], rainfall=result['observedRainfall'],
                resultSha256=sha(path / 'observed-surface-result.json'))
        except FloodModelError as error:
            row.update(status='FAILED', code=str(error),
                       failureSha256=sha(path / 'observed-surface-failure.json'))
        report['cases'].append(row)
        print(name, row['status'], row.get('final'), flush=True)
    if all(name in results for name in ('open-01s', 'open-005s', 'replay-01s', 'closed-01s')):
        a, b = results['open-01s']['final'], results['open-005s']['final']
        report['timeComparison'] = {
            'maximumDepthDifferenceM': max(abs(x-y) for x, y in zip(a['depthM'], b['depthM'])),
            'storageDifferenceM3': a['storageM3'] - b['storageM3'],
            'exactReplay': a == results['replay-01s']['final']}
        report['boundarySensitivity'] = {'closedMinusOpenStorageM3':
            results['closed-01s']['final']['storageM3'] - a['storageM3']}
        require(report['timeComparison']['exactReplay'], 'TERRAIN_REPLAY_MISMATCH')
    report['limitations'] = ['원본 90m DEM 높이의 60분 실제 관측 입력 연결; 현장 침수 깊이 재현 아님',
        '단위는 같은 지역 제품군의 미터 표기에 따른 명시적 해석; 해당 파일의 절대 기준고 미확인',
        '마찰 0·건조 시작·단일 관측소 배정·외곽 경계는 연결 진단 조건',
        '건물·도로 턱·지표 침투·증발산·선행 상태·관망·하천 외부 조건 미포함',
        '2025판 지형과 2022 강우의 스트레스 시험이며 당시 재해 복원·경쟁 순위 사용 불가']
    report['files'] = {str(p.relative_to(directory)): sha(p)
                       for p in sorted(directory.rglob('*')) if p.is_file()}
    write(directory / 'manifest.json', report)
    require(all(row['status'] == 'PASSED' for row in report['cases']), 'TERRAIN_DIAGNOSTIC_FAILED')
    print(json.dumps({key: report[key] for key in ('timeComparison', 'boundarySensitivity')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
