"""평가 기간·노출영역 원 지표의 실제 엔진 결과와 재현 사본 보존."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'simulation'))

from waterleague_sim.engine.coupled_flood import run_coupled
from waterleague_sim.engine.flood_errors import require
from waterleague_sim.engine.flood_process import EngineProcess
from waterleague_sim.engine.network_metrics import library_path
from waterleague_sim.reference.flood_cases import coupled_case, coupled_slope_case, mesh


def metrics(count, start, end):
    return {'schemaVersion': 1, 'policyVersion': 'NUMERICAL_METRICS_v1',
            'evidence': 'NUMERICAL_TEST_ONLY_NOT_SEOUL_EXPOSURE',
            'startMilliseconds': start, 'endMilliseconds': end,
            'networkOutfalls': ['OUT'], 'exposureTriangles': list(range(count)),
            'wetDepthThresholdM': .001}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    directory = args.output.resolve()
    require(not directory.exists(), 'BENCHMARK_OUTPUT_EXISTS')
    directory.mkdir(parents=True)
    paths = [Path(__file__), ROOT / 'scripts/build_network_swmm.py', ROOT / 'scripts/build_live_swmm.py',
             ROOT / 'simulation/waterleague_sim/reference/flood_cases.py',
             *[ROOT / 'simulation/waterleague_sim/engine' / f'{name}.py' for name in (
                'coupled_flood', 'flood_metrics', 'network_metrics', 'network', 'network_quality', 'network_exchange',
                'surface', 'surface_exchange', 'flood_process', 'flood_errors', 'swmm')],
             *[ROOT / 'simulation/native' / f'{name}.inc' for name in (
                'network_snapshot', 'network_exchange', 'network_metrics')],
             ROOT / 'simulation/uv.lock', ROOT / 'simulation/pyproject.toml',
             ROOT / 'data/manifests/anuga-4.0.1.json']
    for path in paths:
        target = directory / 'source' / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    engine = directory / 'engine'
    engine.mkdir()
    for path in (library_path(), library_path().parent / 'network-build.json'):
        shutil.copyfile(path, engine / path.name)
    results = []
    for case in ('surcharge-reentry-window', 'downhill-exposure', 'reverse-boundary', 'known-failed-conduit'):
        model = coupled_slope_case() if case == 'downhill-exposure' else coupled_case(
            initial_network=0 if case == 'reverse-boundary' else 2,
            conduit=case == 'known-failed-conduit')
        if case == 'reverse-boundary':
            model['durationSeconds'] = 5
            model['network']['inputText'] = model['network']['inputText'].replace('OUT 0 FIXED 0 NO',
                                                                                 'OUT 0 FIXED 2 NO')
        start = 10_000 if case == 'surcharge-reentry-window' else 0
        end = 110_000 if case == 'surcharge-reentry-window' else model['durationSeconds'] * 1000
        model['evaluationMetrics'] = metrics(len(model['surface']['triangles']), start, end)
        result = run_coupled(model, directory / case)
        row = {'case': case, 'numericalStatus': result['numericalStatus'],
               'balance': result['balance'], 'evaluationMetrics': result['evaluationMetrics']}
        results.append(row)
        print(json.dumps({'case': case, 'numericalStatus': result['numericalStatus'],
                          'raw': result['evaluationMetrics']['raw']}, ensure_ascii=False), flush=True)
    rain = mesh(2, 2, 2, 2)
    rain['maxStepSeconds'] = .1
    rain['evaluationMetrics'] = metrics(len(rain['triangles']), 1250, 4750)
    with EngineProcess('surface', rain, directory / 'analytical-rain') as surface:
        surface.call('set_rainfall', [60.] * len(rain['triangles']))
        surface.call('advance', 5)
        result = surface.call('finish')
    expected = 4 * 60 / 3_600_000 * (4.75**2 - 1.25**2) / 2 / 3600
    results.append({'case': 'analytical-rain', 'numericalStatus': result['numericalStatus'],
        'evaluationMetrics': result['evaluationMetrics'], 'expectedDepthAreaTimeM3Hours': expected,
        'differenceM3Hours': result['evaluationMetrics']['depthAreaTimeM3Hours'] - expected})
    summary = {'schemaVersion': 1, 'classification': 'NUMERICAL_EVIDENCE_NOT_SEOUL_VALIDATION',
        'cases': results, 'limitations': ['서울 노출영역·연결망·현장 침수 대조 미완료',
            '선형 시간 보간과 내부 끝점 극값; 연속 해석해의 정확한 첨두 보장 아님',
            '총점·공유 귀속·주간/재해 운영 순위 미연결'],
        'files': {str(p.relative_to(directory)): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in sorted(directory.rglob('*')) if p.is_file()}}
    (directory / 'manifest.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    main()
