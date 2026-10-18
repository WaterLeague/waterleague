"""공개 DEM 적분과 저류지 용량 보고의 원 수리 계산 비개입 확인."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'simulation'), str(ROOT)]
from waterleague_sim.engine.coupled_flood import run_coupled
from waterleague_sim.engine.flood_errors import require
from waterleague_sim.engine.surface_basin import compile_basin
from waterleague_sim.evaluation.coupled_adapter import engine_signature, read_coupled_record
from waterleague_sim.reference.surface_basin import case
from waterleague_sim.terrain.storage import stage_storage
from waterleague_sim.evaluation.values import digest
from simulation.tests.test_flood_attribution import policy


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    directory = args.output.resolve()
    require(not directory.exists(), 'STORAGE_EVIDENCE_OUTPUT_EXISTS')
    directory.mkdir(parents=True)
    archive = ROOT/'data/runs/ngii-surface-rainfall-20261018-v1'
    manifest = archive/'manifest.json'
    require(sha(manifest) == 'c5ce550dcd54aaecbf4775c807371f89b90517ee5bfc2a2bb354f805ea4a8a6d',
            'STORAGE_TERRAIN_ARCHIVE_MISMATCH')
    registry = json.loads(manifest.read_bytes())
    source = archive/'terrain/surface-input.json'
    require(sha(source) == registry['files']['terrain/surface-input.json'], 'STORAGE_TERRAIN_SOURCE_MISMATCH')
    shutil.copyfile(source, directory/'public-surface-input.json')
    shutil.copyfile(manifest, directory/'public-source-manifest.json')
    surface = json.loads(source.read_bytes())
    low, high = min(surface['elevationM']), max(surface['elevationM'])
    levels = sorted({low+(high-low)*i/256 for i in range(256)} | {high})
    curve = stage_storage(surface, list(range(len(surface['triangles']))), levels)
    require(curve == stage_storage(surface, list(range(len(surface['triangles']))), levels),
            'STORAGE_TERRAIN_REPLAY_MISMATCH')
    write(directory/'public-terrain-stage-storage.json', curve)
    model = case()
    old = deepcopy(model)
    old['surfaceBasinDesign']['schemaVersion'] = 1
    original, previous = compile_basin(old)
    current, metadata = compile_basin(model)
    require(original == current, 'STORAGE_HYDRAULIC_INPUT_CHANGED')
    write(directory/'design-input.json', model)
    write(directory/'derived-model.json', current)
    write(directory/'basin-design.json', metadata)
    before, after = run_coupled(old, directory/'v1'), run_coupled(model, directory/'v2')
    require(before['numericalStatus'] == after['numericalStatus'] == 'PASSED', 'STORAGE_NATIVE_FAILED')
    for file in ('network/network.out', 'surface/surface-result.json'):
        require((directory/'v1'/file).read_bytes() == (directory/'v2'/file).read_bytes(),
                'STORAGE_NATIVE_PHYSICS_CHANGED')
    require(before['balance'] == after['balance'] and before['evaluationMetrics'] == after['evaluationMetrics'],
            'STORAGE_METRICS_CHANGED')
    for version, result in (('v1', before), ('v2', after)):
        root = directory/version
        network = json.loads((root/'network/network-result.json').read_bytes())
        output = json.loads((root/'surface/surface-result.json').read_bytes())
        context = policy()['context'] | {'metricSpecificationSha256': digest(result['evaluationMetrics']['specification']),
            'engineSha256': engine_signature(network, output, result)}
        require(read_coupled_record(root, sha(root/'coupled-result.json'), context)['complete'],
                'STORAGE_RESEARCH_READER_FAILED')
    report = {'schemaVersion': 1, 'classification': 'PUBLIC_TERRAIN_GEOMETRIC_STORAGE_NOT_FLOOD_PREDICTION',
        'rankingEligible': False, 'sourceSurfaceSha256': sha(source),
        'sourceRasterFiles': surface['terrainProvenance']['sourceFiles'],
        'verticalReference': surface['terrainProvenance']['verticalReference'],
        'publicTerrain': {'triangles': len(curve['triangles']), 'stages': len(curve['levels']),
            'areaM2': curve['planAreaM2'], 'maximumLinearMinusCentroidM3':
                max(row['linearMinusCentroidStorageM3'] for row in curve['levels']),
            'exactReplay': True},
        'basin': {'unchangedHydraulicInputs': original == current, 'nativeOutExact': True,
            'surfaceResultExact': True, 'balanceAndMetricsExact': True, 'researchVersionsRead': [1, 2],
            'capacityAtLowestBankM3': metadata['facilities'][0]['terrainStageStorage']['levels'][-1]['storageM3'],
            'maximumLinearMinusCentroidM3': max(row['linearMinusCentroidStorageM3']
                for row in metadata['facilities'][0]['terrainStageStorage']['levels'])},
        'limitations': curve['limitations'] + ['성수 사각 창의 모든 낮은 지형에 같은 수위를 놓은 적분이며 실제 연결 저류지가 아님',
            '공개 DEM의 원 해상도·수직 기준 한계 유지; 수리 경계·관망 연결과 지도 설치 미완료']}
    sources = [Path(__file__)]
    for relative in ('simulation/waterleague_sim',):
        sources.extend(sorted((ROOT/relative).rglob('*.py')))
    for source in sources:
        target = directory/'source'/source.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    report['files'] = {str(p.relative_to(directory)): sha(p) for p in sorted(directory.rglob('*')) if p.is_file()}
    write(directory/'manifest.json', report)
    print(json.dumps({k: v for k, v in report.items() if k != 'files'}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
