"""원 체적·내부 수렴 판정의 실제 엔진 결과와 입력/코드 해시 보존."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'simulation'))

from waterleague_sim.engine import network, network_exchange, network_metrics, swmm
from waterleague_sim.engine.coupled_flood import run_coupled
from waterleague_sim.engine.flood_errors import require, FloodModelError
from waterleague_sim.reference.flood_cases import conduit_drainage_case, coupled_case


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    require(not output.exists(), 'BENCHMARK_OUTPUT_EXISTS')
    output.mkdir(parents=True)
    paths = [Path(__file__), ROOT / 'simulation/waterleague_sim/reference/flood_cases.py',
             ROOT / 'scripts/build_network_swmm.py', ROOT / 'scripts/build_live_swmm.py',
             *[ROOT / 'simulation/native' / (name + '.inc') for name in (
                 'network_snapshot', 'network_exchange', 'network_metrics')],
             *[ROOT / 'simulation/waterleague_sim/engine' / (name + '.py') for name in (
                 'network', 'network_exchange', 'network_metrics', 'network_quality', 'coupled_flood',
                 'flood_errors', 'flood_process', 'flood_metrics', 'surface', 'surface_exchange', 'swmm')],
             ROOT / 'simulation/pyproject.toml', ROOT / 'simulation/uv.lock',
             ROOT / 'data/manifests/anuga-4.0.1.json']
    for path in paths:
        target = output / 'source' / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    engine_hashes = {name: digest(module.library_path()) for name, module in (
        ('lid', swmm), ('network', network), ('exchange', network_exchange), ('metrics', network_metrics))}
    for name, module in (('network', network), ('exchange', network_exchange), ('metrics', network_metrics)):
        directory = output / 'engine' / name
        directory.mkdir(parents=True)
        for path in (module.library_path(), module.library_path().parent / 'network-build.json'):
            shutil.copyfile(path, directory / path.name)
    results = []
    for name, model in (
        ('small-volume-reported-zero', conduit_drainage_case()),
        ('low-mass-error-nonconverged', conduit_drainage_case(5)),
        ('original-wet-tank-conduit', coupled_case(conduit=True)),
    ):
        with network.NetworkSession(model['network']['inputText'], output / name,
                                    evaluation_seconds=120) as engine:
            engine.advance(120)
            result = engine.finish()
        results.append({'case': name, 'reportedRoutingContinuityPercent': result['routingContinuityPercent'],
                        'convergence': result['convergence'], 'quality': result['numericalQuality']})
        print(json.dumps(results[-1], ensure_ascii=False), flush=True)
    for name, model in (('coupled-valid-reentry', coupled_case()),
                        ('coupled-nonconverged', conduit_drainage_case(5))):
        model['evaluationMetrics'] = {'schemaVersion': 1, 'policyVersion': 'NUMERICAL_QUALITY_v1',
            'evidence': 'NUMERICAL_TEST_ONLY', 'startMilliseconds': 0, 'endMilliseconds': 120000,
            'networkOutfalls': ['OUT'], 'exposureTriangles': list(range(len(model['surface']['triangles']))),
            'wetDepthThresholdM': .001}
        try:
            result = run_coupled(model, output / name)
        except FloodModelError as error:
            require(name == 'coupled-nonconverged' and str(error) == 'COUPLED_UNMAPPED_NODE_FLOODING',
                    'UNEXPECTED_NUMERICAL_FAILURE')
            failure = json.loads((output / name / 'coupled-failure.json').read_text())
            results.append({'case': name, 'numericalStatus': 'FAILED', 'failure': failure})
            print(json.dumps({'case': name, 'status': 'FAILED', 'code': str(error)}, ensure_ascii=False), flush=True)
            continue
        results.append({'case': name, 'numericalStatus': result['numericalStatus'],
            'convergence': result['networkConvergence'], 'quality': result['networkNumericalQuality'],
            'balance': result['balance'], 'evaluationMetrics': result['evaluationMetrics']})
        print(json.dumps({'case': name, 'status': result['numericalStatus']}, ensure_ascii=False), flush=True)
    manifest = {'schemaVersion': 1, 'classification': 'NUMERICAL_EVIDENCE_NOT_SEOUL_VALIDATION',
        'engineSha256': engine_hashes, 'cases': results,
        'limitations': ['단일 저장조/관로의 원래 수지 실패 미해결',
            '보고값 축약·비수렴 성공 오판 차단이며 엔진 수리식 변경 없음',
            '서울 공개 연결 관망·현장 침수 정확도와 순위 연결 미완료'],
        'files': {str(p.relative_to(output)): digest(p) for p in sorted(output.rglob('*')) if p.is_file()}}
    (output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    main()
