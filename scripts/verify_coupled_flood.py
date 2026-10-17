"""관망·지표 양방향 교환의 수치 사례와 재현 묶음 생성."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'simulation'))

from waterleague_sim.engine.coupled_flood import run_coupled
from waterleague_sim.engine.flood_errors import require
from waterleague_sim.engine import swmm
from waterleague_sim.reference.flood_cases import coupled_case, coupled_slope_case, coupled_limited_case


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    require(not output.exists(), 'BENCHMARK_OUTPUT_EXISTS')
    output.mkdir(parents=True)
    paths = [Path(__file__), ROOT / 'scripts/build_network_swmm.py', ROOT / 'scripts/build_live_swmm.py',
             ROOT / 'simulation/waterleague_sim/reference/flood_cases.py',
             *[ROOT / 'simulation/waterleague_sim/engine' / f'{name}.py' for name in
               ('coupled_flood', 'network', 'network_exchange', 'surface', 'surface_exchange', 'flood_process',
                'flood_errors', 'swmm')],
             ROOT / 'simulation/native/network_snapshot.inc', ROOT / 'simulation/native/network_exchange.inc',
             ROOT / 'simulation/uv.lock', ROOT / 'simulation/pyproject.toml',
             ROOT / 'data/manifests/anuga-4.0.1.json']
    for path in paths:
        target = output / 'source' / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    results = []
    for step in (200, 100, 50):
        case = f'surcharge-reentry-{step}ms'
        result = run_coupled(coupled_case(exchange_ms=step), output / case)
        row = {key: result[key] for key in ('balance', 'numericalStatus', 'networkRoutingContinuityPercent',
                                           'steps', 'smallestExchangeMilliseconds')}
        row['case'] = case
        results.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
    failed_conduit = run_coupled(coupled_case(conduit=True), output / 'small-tank-conduit')
    results.append({'case': 'small-tank-conduit', 'balance': failed_conduit['balance'],
                    'numericalStatus': failed_conduit['numericalStatus'],
                    'networkRoutingContinuityPercent': failed_conduit['networkRoutingContinuityPercent']})
    fixed = output / 'small-tank-conduit'
    executable = swmm.library_path().parent / 'runswmm'
    subprocess.run([str(executable), str(fixed / 'network/network.inp'),
                    str(fixed / 'stock-fixed-boundary.rpt'), str(fixed / 'stock-fixed-boundary.out')],
                   capture_output=True, check=True, timeout=60)
    errors = re.findall(r'Continuity Error \(%\)\s*\.+\s*([-+\d.]+)',
                        (fixed / 'stock-fixed-boundary.rpt').read_text(encoding='cp1252'))
    require(len(errors) == 1, 'COUPLED_STOCK_DIAGNOSTIC_INVALID')
    results[-1]['stockFixedBoundaryDiagnostic'] = {
        'classification': 'SEPARATE_FIXED_BOUNDARY_NOT_COUPLED_REPLAY',
        'routingContinuityPercent': float(errors[0]),
        'executableSha256': hashlib.sha256(executable.read_bytes()).hexdigest()}
    slope = run_coupled(coupled_slope_case(), output / 'local-surcharge-slope')
    fields = json.loads((output / 'local-surcharge-slope/surface/surface-result.json').read_text())['final']
    results.append({'case': 'local-surcharge-slope', 'balance': slope['balance'],
                    'numericalStatus': slope['numericalStatus'],
                    'wetTriangles': sum(depth > .001 for depth in fields['depthM']),
                    'maxVelocityXMps': max(abs(v) for v in fields['velocityXMps'])})
    limited = run_coupled(coupled_limited_case(), output / 'limited-surface-water')
    results.append({'case': 'limited-surface-water', 'balance': limited['balance'],
                    'numericalStatus': limited['numericalStatus'],
                    'smallestExchangeMilliseconds': limited['smallestExchangeMilliseconds']})
    for case, rain in (('dry-idle', False), ('rain-on-dry', True)):
        model = coupled_case(initial_network=0)
        model['durationSeconds'] = 5
        if rain:
            model['surfaceRainfall'] = [{'timeMilliseconds': 0, 'ratesMmH': [60.] * len(model['surface']['triangles']),
                                        'evidence': 'NUMERICAL_TEST_ONLY'}]
        result = run_coupled(model, output / case)
        results.append({'case': case, 'balance': result['balance'], 'numericalStatus': result['numericalStatus']})
    summary = {'schemaVersion': 1, 'classification': 'NUMERICAL_EVIDENCE_NOT_SEOUL_VALIDATION',
               'cases': results, 'limitations': ['공개 서울 연결 관망·지표 입력과 침수흔적 대조 미완료',
                   '명시적 분할과 영역 평균 수두; 지표 침투·증발산 전체 수지 미연결'],
               'files': {str(p.relative_to(output)): hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in sorted(output.rglob('*')) if p.is_file()}}
    (output / 'manifest.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    main()
