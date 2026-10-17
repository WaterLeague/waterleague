"""시설 제원 고정 상태의 압력 해법·초기화·교환 간격 비교와 원본 보존."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'simulation'))

from waterleague_sim.engine import network, network_exchange, network_metrics, swmm
from waterleague_sim.engine.coupled_flood import run_coupled
from waterleague_sim.engine.flood_errors import require
from waterleague_sim.reference.flood_cases import (
    coupled_case, conduit_drainage_case, coupled_conduit_surcharge_case)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    output = parser.parse_args().output.resolve()
    require(not output.exists(), 'BENCHMARK_OUTPUT_EXISTS')
    output.mkdir(parents=True)
    paths = [Path(__file__), ROOT / 'scripts/build_network_swmm.py', ROOT / 'scripts/build_live_swmm.py',
             ROOT / 'simulation/waterleague_sim/reference/flood_cases.py',
             *[ROOT / 'simulation/waterleague_sim/engine' / (name + '.py') for name in (
                 'network', 'network_quality', 'network_exchange', 'network_metrics', 'coupled_flood',
                 'flood_errors', 'flood_process', 'flood_metrics', 'surface', 'surface_exchange', 'swmm')],
             *[ROOT / 'simulation/native' / (name + '.inc') for name in (
                 'network_snapshot', 'network_exchange', 'network_metrics')],
             ROOT / 'simulation/uv.lock', ROOT / 'simulation/pyproject.toml',
             ROOT / 'data/manifests/anuga-4.0.1.json']
    for path in paths:
        target = output / 'source' / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    engines = {name: digest(module.library_path()) for name, module in (
        ('lid', swmm), ('network', network), ('exchange', network_exchange), ('metrics', network_metrics))}
    for name, module in (('network', network), ('exchange', network_exchange), ('metrics', network_metrics)):
        directory = output / 'engine' / name
        directory.mkdir(parents=True)
        for path in (module.library_path(), module.library_path().parent / 'network-build.json'):
            shutil.copyfile(path, directory / path.name)
    archive = ROOT / 'tmp/swmm/source.tar.gz'
    require(digest(archive) == network.identity()['sourceArchiveSha256'], 'EPA_SOURCE_HASH_MISMATCH')
    with tarfile.open(archive) as bundle:
        prefix = bundle.getmembers()[0].name.split('/')[0]
        target = output / 'epa-source'
        target.mkdir()
        for name in ('dwflow.c', 'dynwave.c', 'flowrout.c'):
            raw = bundle.extractfile(f'{prefix}/src/solver/{name}').read()
            (target / name).write_bytes(raw)
    results = []
    for method in ('EXTRAN', 'SLOT'):
        for wet in (True, False):
            for step in (10, 1):
                if wet:
                    inp = coupled_case(conduit=True)['network']['inputText']
                    inp = inp.replace('FLOW_ROUTING DYNWAVE', f'FLOW_ROUTING DYNWAVE\nSURCHARGE_METHOD {method}')
                    inp = inp.replace('ROUTING_STEP 0.01', f'ROUTING_STEP {step / 1000}')
                    inp = inp.replace('MINIMUM_STEP 0.01', f'MINIMUM_STEP {step / 1000}')
                    inp = inp.replace('MAX_TRIALS 40', 'MAX_TRIALS 200')
                else:
                    inp = conduit_drainage_case(route_ms=step, surcharge_method=method)['network']['inputText']
                name = f"{'wet' if wet else 'dry'}-{method}-{step}ms"
                frames = []
                with network.NetworkSession(inp, output / name, evaluation_seconds=120) as s:
                    frames.append(s.initial)
                    for _ in range(120):
                        frames.append(s.advance(1))
                    result = s.finish()
                (output / name / 'frames.json').write_text(json.dumps(frames, allow_nan=False) + '\n')
                results.append({'case': name, 'quality': result['numericalQuality'],
                                'configuration': result['numericalConfiguration'],
                                'convergence': result['convergence']})
                print(name, result['numericalStatus'], flush=True)
    for name, parameters in (
        ('coupled-conduit-100ms', {}),
        ('coupled-conduit-route10ms', {'route_ms': 10}),
        ('coupled-conduit-50ms', {'exchange_ms': 50}),
        ('coupled-conduit-mesh8', {'nx': 8}),
    ):
        result = run_coupled(coupled_conduit_surcharge_case(**parameters), output / name)
        results.append({'case': name, 'numericalStatus': result['numericalStatus'],
                        'balance': result['balance'], 'quality': result['networkNumericalQuality'],
                        'configuration': result['networkNumericalConfiguration'],
                        'convergence': result['networkConvergence'],
                        'rawMetrics': result['evaluationMetrics']['raw'], 'rankingEligible': False})
        print(name, result['numericalStatus'], flush=True)
    frames = json.loads((output / 'wet-EXTRAN-10ms/frames.json').read_text())
    full = frames[2:31]
    require(all(abs(f['links']['PIPE']['depthM'] - .15) < 1e-12 for f in full),
            'DIAGNOSTIC_FULL_CONDUIT_REQUIRED')
    # 원형 단면의 해석 폭 근사와 실제 오차 증가 비교이며 계산 보정에 사용하지 않는다.
    area = 10 / 2 * 2 * math.sqrt((.96 * .15) * (.04 * .15))
    head_drop = full[0]['nodes']['TANK']['headM'] - full[-1]['nodes']['TANK']['headM']
    observed = full[0]['totals']['balanceResidualM3'] - full[-1]['totals']['balanceResidualM3']
    diagnostic = {'intervalSeconds': [2, 30], 'pipeDiameterM': .15, 'pipeLengthM': 10,
        'crownCutoff': .96, 'minimumTopWidthAreaApproximationM2': area,
        'storageHeadDropM': head_drop, 'predictedExcessVolumeM3': area * head_drop,
        'observedExcessVolumeGrowthM3': observed,
        'predictionDifferenceM3': observed - area * head_drop,
        'initialPipeDepthM': frames[0]['links']['PIPE']['depthM'],
        'classification': 'SOURCE_PATH_DIAGNOSTIC_NOT_VOLUME_CORRECTION'}
    manifest = {'schemaVersion': 1, 'classification': 'NUMERICAL_EVIDENCE_NOT_SEOUL_VALIDATION',
        'engineSha256': engines, 'cases': results, 'fullPipeStorageDiagnostic': diagnostic,
        'limitations': ['젖은 초기 상태 단일 관로의 수지 실패 미해결',
            '공식 SLOT의 가상 슬롯과 명시적 결합의 수치 근사 유지',
            '평탄한 합성 격자의 비교이며 실제 지형 공간 수렴·서울 현장 검증 아님',
            '실제 선행 관측 초기화·공개 연결 관망·새 순위 연결 미완료'],
        'files': {str(p.relative_to(output)): digest(p) for p in sorted(output.rglob('*')) if p.is_file()}}
    (output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    main()
