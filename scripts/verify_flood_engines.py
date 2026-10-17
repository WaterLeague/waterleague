"""관망·2D 엔진의 공개 참조와 해석 사례 실행 및 재현 근거 저장."""
import argparse
import hashlib
from io import BytesIO
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'simulation'))

from waterleague_sim.engine import network, swmm
from waterleague_sim.engine.flood_errors import FloodModelError, require
from waterleague_sim.engine.flood_process import EngineProcess
from waterleague_sim.reference.epa import read_sources
from waterleague_sim.reference.flood_cases import mesh, tank_input


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--source', type=Path, default=ROOT / 'tmp/epa-reference/applications.zip')
    args = parser.parse_args()
    output = args.output.resolve()
    require(not output.exists(), 'BENCHMARK_OUTPUT_EXISTS')
    provenance, _ = read_sources(args.source)
    output.mkdir(parents=True)
    source_paths = [Path(__file__), ROOT / 'simulation/waterleague_sim/reference/flood_cases.py',
                    ROOT / 'simulation/waterleague_sim/engine/flood_errors.py',
                    ROOT / 'simulation/waterleague_sim/engine/flood_process.py',
                    ROOT / 'simulation/waterleague_sim/engine/flood_metrics.py',
                    ROOT / 'simulation/waterleague_sim/engine/network.py',
                    ROOT / 'simulation/waterleague_sim/engine/network_quality.py',
                    ROOT / 'simulation/waterleague_sim/engine/surface.py',
                    ROOT / 'simulation/native/network_snapshot.inc',
                    ROOT / 'simulation/pyproject.toml', ROOT / 'simulation/uv.lock',
                    ROOT / 'data/manifests/anuga-4.0.1.json', ROOT / 'scripts/build_network_swmm.py',
                    ROOT / 'scripts/build_live_swmm.py']
    for path in source_paths:
        target = output / 'source' / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    with ZipFile(args.source) as outer:
        with ZipFile(BytesIO(outer.read(provenance['nestedArchive']['member']))) as inner:
            originals = {name: inner.read(name) for name in ('Example3.inp', 'Example8.inp')}
    results = {'schemaVersion': 1, 'classification': 'NUMERICAL_EVIDENCE_NOT_SEOUL_VALIDATION',
               'networkCases': [], 'surfaceCases': [], 'reference': {
                   'archiveUrl': provenance['archiveUrl'], 'archiveSha256': provenance['archiveSha256'],
                   'inputs': {name: hashlib.sha256(raw).hexdigest() for name, raw in originals.items()}},
               'sourceCode': {str(p.relative_to(ROOT)): digest(p) for p in source_paths}}
    for name, raw in originals.items():
        directory = output / name.removesuffix('.inp')
        with EngineProcess('network', raw.decode('cp1252'), directory) as session:
            completed = session.call('run')
            result = completed['result']
        subprocess.run([str(swmm.library_path().parent / 'runswmm'), str(directory / 'network.inp'),
                        str(directory / 'stock.rpt'), str(directory / 'stock.out')],
                       check=True, capture_output=True, timeout=60)
        equal = (directory / 'network.out').read_bytes() == (directory / 'stock.out').read_bytes()
        require(equal, 'NETWORK_STOCK_OUTPUT_MISMATCH')
        warning_lines = re.findall(r'^.*WARNING.*$', (directory / 'network.rpt').read_text(encoding='cp1252'), re.M)
        results['networkCases'].append({'case': name, 'stockBinaryOutputEqual': equal,
            'routingContinuityPercent': result['routingContinuityPercent'],
            'numericalStatus': result['numericalStatus'], 'maximumPumpFlowM3s': completed['maximumPumpFlowM3s'],
            'warnings': [line.strip() for line in warning_lines], 'totals': result['final']['totals'],
            'resultSha256': digest(directory / 'network-result.json')})
    with EngineProcess('network', tank_input(), output / 'boundary-reversal', evaluation_seconds=120) as session:
        session.call('set_outfall_head', 'OUT', 2)
        reverse = session.call('advance', 30)
        session.call('set_outfall_head', 'OUT', 0)
        session.call('set_inflow', 'TANK', .02)
        forward = session.call('advance', 90)
        result = session.call('finish')
        require(reverse['links']['PIPE']['flowM3s'] < 0 < forward['links']['PIPE']['flowM3s'],
                'NETWORK_REVERSAL_MISSING')
        results['networkCases'].append({'case': 'ANALYTICAL_BOUNDARY_REVERSAL',
            'reverseFlowM3s': reverse['links']['PIPE']['flowM3s'],
            'forwardFlowM3s': forward['links']['PIPE']['flowM3s'],
            'routingContinuityPercent': result['routingContinuityPercent'],
            'numericalStatus': result['numericalStatus'],
            'resultSha256': digest(output / 'boundary-reversal/network-result.json')})
    import numpy as np
    lake = mesh(bed=lambda x, y: .3 * np.sin(x / 20 * np.pi), water=lambda x, z: 1 - z)
    cases = [('lake', lake, 30), ('rain', mesh(), 60)]
    cases += [(f'dam-break-{nx}', mesh(nx, 5, 200, 10, water=lambda x, z: (x < 100).astype(float)), 5)
              for nx in (100, 200)]
    for name, model, duration in cases:
        with EngineProcess('surface', model, output / name) as session:
            if name == 'rain':
                session.call('set_rainfall', [60.] * len(model['triangles']))
            final = session.call('advance', duration)
            result = session.call('finish')
        row = {'case': name, 'triangles': len(model['triangles']),
               'numericalStatus': result['numericalStatus'], 'storageM3': final['storageM3'],
               'balanceResidualM3': final['balanceResidualM3'],
               'maxVelocityMps': float(max(np.hypot(final['velocityXMps'], final['velocityYMps']))),
               'resultSha256': digest(output / name / 'surface-result.json')}
        if name.startswith('dam-break'):
            points, triangles = np.asarray(model['verticesM']), np.asarray(model['triangles'])
            areas = np.abs(np.linalg.det(np.stack((points[triangles[:, 1]] - points[triangles[:, 0]],
                           points[triangles[:, 2]] - points[triangles[:, 0]]), axis=1))) / 2
            x = points[triangles, 0].mean(axis=1) - 100
            gravity = result['gravityMps2']
            c = np.sqrt(gravity)
            expected = np.where(x < -5*c, 1, np.where(x > 10*c, 0, (2*c - x/5)**2 / (9*gravity)))
            row['analyticalDepthAreaWeightedMaeM'] = float(np.average(
                abs(np.asarray(final['depthM']) - expected), weights=areas))
        results['surfaceCases'].append(row)
    results['limitations'] = ['서울 관망·2D 결합·공개 침수흔적 대조 미완료',
        'EPA 예제의 수치 실패·경고 보존, 인쇄 보고서 참조값과의 독립 대조 아님',
        '2D 해석 사례의 마찰·지형·경계는 명시한 시험 조건, 서울 관측 입력 아님',
        '지표 침투·증발산·시설·양방향 체적 교환은 후속 연결 대상']
    results['files'] = {str(p.relative_to(output)): digest(p)
                        for p in sorted(output.rglob('*')) if p.is_file()}
    (output / 'manifest.json').write_text(json.dumps(results, ensure_ascii=False, allow_nan=False, indent=2) + '\n')
    print(json.dumps({key: results[key] for key in ('networkCases', 'surfaceCases')}, ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except FloodModelError as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
