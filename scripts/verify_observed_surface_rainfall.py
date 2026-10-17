"""실제 AWS 강우의 지표·관망 연결 및 실패/시간 간격 비교 산출물 보존."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'simulation'))

from waterleague_sim.engine.coupled_flood import run_coupled
from waterleague_sim.engine.flood_errors import FloodModelError, require
from waterleague_sim.forcing.surface_run import run_observed_surface
from waterleague_sim.reference.flood_cases import mesh, coupled_case


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def specification(model, *, minutes=359, two_stations=True):
    from datetime import datetime, timezone, timedelta
    start = datetime(2022, 8, 8, 9, tzinfo=timezone.utc)
    sources = [('421', '21d21033308e31deafe9190f5a0723fded9e43562a0d7c5573cc94c3e99efd96'),
               ('401', '39ce4686facc74c09f13c2911162ea0293a30a8cac410da821a5fa51a423f21c')]
    return {'schemaVersion': 1, 'startUtc': start.isoformat(),
            'endUtc': (start + timedelta(minutes=minutes)).isoformat(),
            'assignmentEvidence': '실제 성동/서초 강우의 합성 격자 배정; 서울 위치·유역 재현 아님',
            'stations': [{'file': f'kma-{sid}-202208081800-202208082359-disaster-v1.json', 'sha256': sha}
                         for sid, sha in sources[:2 if two_stations else 1]],
            'stationByTriangle': ['401' if two_stations and i % 2 else '421'
                                  for i in range(len(model['triangles']))]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    directory = args.output.resolve()
    require(not directory.exists(), 'OBSERVED_RAIN_OUTPUT_EXISTS')
    directory.mkdir(parents=True)
    sources = [Path(__file__), ROOT / 'simulation/uv.lock', ROOT / 'simulation/pyproject.toml',
               ROOT / 'data/manifests/anuga-4.0.1.json']
    for folder in ('forcing', 'ingestion', 'engine', 'reference'):
        sources.extend(sorted((ROOT / 'simulation/waterleague_sim' / folder).glob('*.py')))
    for source in sources:
        target = directory / 'source' / source.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    report = {'schemaVersion': 1, 'classification': 'OBSERVED_RAIN_ON_SYNTHETIC_HYDRAULICS',
              'rankingEligible': False, 'cases': [], 'sourceCode': {
                  str(source.relative_to(ROOT)): digest(source) for source in sources}}
    results = {}
    for name, step in [('step-30s', 30.), ('step-1s', 1.), ('step-01s', .1),
                       ('step-005s', .05), ('replay-01s', .1)]:
        model = mesh(2, 2)
        model['maxStepSeconds'] = step
        path = directory / name
        try:
            result = run_observed_surface(model, specification(model), path)
            results[name] = result
            report['cases'].append({'name': name, 'maximumStepSeconds': step,
                'status': result['numericalStatus'], 'final': result['final'],
                'rainfall': result['observedRainfall'],
                'maximumForcingBoundaryBalanceResidualM3': result['maximumForcingBoundaryBalanceResidualM3'],
                'resultSha256': digest(path / 'observed-surface-result.json')})
        except FloodModelError as error:
            failure = json.loads((path / 'observed-surface-failure.json').read_bytes())
            report['cases'].append({'name': name, 'maximumStepSeconds': step, 'status': 'FAILED',
                'code': str(error), 'lastTimeSeconds': failure['lastSurface']['timeSeconds'],
                'maximumForcingBoundaryBalanceResidualM3': failure['maximumForcingBoundaryBalanceResidualM3'],
                'failureSha256': digest(path / 'observed-surface-failure.json')})
        print(name, report['cases'][-1]['status'], flush=True)
    require(results['step-01s']['final'] == results['replay-01s']['final'], 'OBSERVED_RAIN_REPLAY_MISMATCH')
    a, b = (results[name]['final'] for name in ('step-01s', 'step-005s'))
    report['timeComparison'] = {
        'maximumStepsSeconds': [.1, .05],
        'maximumDepthDifferenceM': max(abs(x-y) for x, y in zip(a['depthM'], b['depthM'])),
        'storageDifferenceM3': a['storageM3'] - b['storageM3'], 'exactReplay': True}
    model = coupled_case(initial_network=0, exchange_ms=500)
    model['network']['inputText'] = model['network']['inputText'].replace('01/01/2020', '08/08/2022')
    model['network']['inputText'] = model['network']['inputText'].replace('00:00:00', '09:00:00')
    model['network']['inputText'] = model['network']['inputText'].replace('00:02:01', '09:02:01')
    model['network']['timeZone'] = 'UTC'
    model['observedRainfall'] = specification(model['surface'], minutes=2, two_stations=False)
    result = run_coupled(model, directory / 'coupled')
    report['coupled'] = {key: result[key] for key in ('numericalStatus', 'balance', 'observedRainfall')}
    report['limitations'] = ['359분 실제 AWS 관측; 격자·경계·관망은 합성 입력 연결 검사',
        '지표 침투·증발산·선행 수분·실제 서울 DEM·관망 연결 미포함',
        '0.1/0.05초는 명시한 수치 비교; 자동 설정 완화·실제 시설 제원 변경 없음',
        '큰 시간 간격의 실패 보존; 모든 유역·격자의 안정성 또는 현장 정확도 근거 아님']
    report['files'] = {str(p.relative_to(directory)): digest(p)
                       for p in sorted(directory.rglob('*')) if p.is_file()}
    (directory / 'manifest.json').write_text(json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2) + '\n')
    print(json.dumps({'comparison': report['timeComparison'], 'coupled': report['coupled']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
