"""공개 DEM 계산의 원 중심 프레임과 관망 교환 출력의 비개입 대조."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'simulation'))
from waterleague_sim.engine.coupled_flood import run_coupled
from waterleague_sim.engine.flood_errors import require
from waterleague_sim.engine.surface_frame_reader import NativeFrameReader
from waterleague_sim.forcing.surface_run import run_observed_surface
from waterleague_sim.reference.flood_cases import coupled_limited_case

OUTPUT = {'schemaVersion': 1, 'type': 'NATIVE_CENTROID_FLOAT64', 'maxFrames': 1000, 'maxBytes': 32*1024**2}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2)+'\n')


def inspect(path, final):
    reader = NativeFrameReader(path, sha(path/'surface-result.json'))
    frame = reader.at_time(final['timeSeconds'])
    require(frame['depthM'] == final['depthM'] and frame['velocityXMps'] == final['velocityXMps']
            and frame['velocityYMps'] == final['velocityYMps'], 'SURFACE_FRAME_NATIVE_MISMATCH')
    for index in range(len(reader.times)):
        reader.frame(index)
    return {'frames': len(reader.times), 'triangles': reader.count,
        'binaryBytes': reader.catalog['binaryBytes'], 'nativeValuesExact': True,
        'finalStorageM3': frame['wholeDomainStorageM3'],
        'storageReconstructionResidualM3': frame['storageReconstructionResidualM3'],
        'catalogSha256': sha(path/'native-frames/catalog.json'),
        'surfaceResultSha256': sha(path/'surface-result.json'),
        'firstTimeSeconds': reader.times[0], 'lastTimeSeconds': reader.times[-1],
        'startUtc': reader.catalog['startUtc'], 'classification': reader.catalog['classification'],
        'rankingEligible': reader.catalog['rankingEligible']}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    directory = args.output.resolve()
    require(not directory.exists(), 'SURFACE_FRAME_VERIFICATION_OUTPUT_EXISTS')
    directory.mkdir(parents=True)
    archive = ROOT/'data/runs/ngii-surface-rainfall-20261018-v1'
    manifest = archive/'manifest.json'
    require(sha(manifest) == 'c5ce550dcd54aaecbf4775c807371f89b90517ee5bfc2a2bb354f805ea4a8a6d',
            'SURFACE_FRAME_TERRAIN_ARCHIVE_MISMATCH')
    registry = json.loads(manifest.read_bytes())
    for relative in ('open-01s/observed-surface-input.json', 'open-01s/observed-surface-result.json'):
        require(sha(archive/relative) == registry['files'][relative], 'SURFACE_FRAME_TERRAIN_SOURCE_MISMATCH')
        shutil.copyfile(archive/relative, directory/Path(relative).name)
    shutil.copyfile(manifest, directory/'terrain-original-manifest.json')
    shutil.copytree(archive/'terrain', directory/'public-terrain')
    source = json.loads((directory/'observed-surface-input.json').read_bytes())
    original = json.loads((directory/'observed-surface-result.json').read_bytes())
    model = source['surface'] | {'frameOutput': OUTPUT}
    result = run_observed_surface(model, source['observedRainfall'], directory/'public-dem')
    require(result['final'] == original['final'], 'SURFACE_FRAME_OUTPUT_CHANGED_PHYSICS')
    terrain = inspect(directory/'public-dem/surface', result['final'])
    terrain.update(originalFinalExact=True, originalResultSha256=sha(directory/'observed-surface-result.json'),
                   rainfall=result['observedRainfall'], numericalQuality=result['numericalQuality'])
    print('public-dem', json.dumps({k: terrain[k] for k in ('frames','triangles','binaryBytes','nativeValuesExact','originalFinalExact')}), flush=True)
    cases, results = [], []
    for name, interval in (('exchange-100ms', 100), ('exchange-1000ms', 1000)):
        coupled = coupled_limited_case()
        coupled['surface'].update(schemaVersion=2, frameOutput=deepcopy(OUTPUT))
        coupled['frameIntervalMilliseconds'] = interval
        value = run_coupled(coupled, directory/name)
        native = json.loads((directory/name/'surface/surface-result.json').read_bytes())
        details = inspect(directory/name/'surface', native['final'])
        details.update(name=name, requestedFrameIntervalMilliseconds=interval, balance=value['balance'])
        cases.append(details)
        results.append(value)
        print(name, details['frames'], details['finalStorageM3'], flush=True)
    require(results[0]['balance'] == results[1]['balance']
            and results[0]['surfaceNumericalQuality'] == results[1]['surfaceNumericalQuality'],
            'SURFACE_FRAME_INTERVAL_CHANGED_PHYSICS')
    sources = [Path(__file__), ROOT/'simulation/uv.lock', ROOT/'data/manifests/anuga-4.0.1.json']
    for folder in ('engine', 'forcing', 'ingestion', 'reference'):
        sources.extend(sorted((ROOT/'simulation/waterleague_sim'/folder).glob('*.py')))
    for source in sources:
        target = directory/'source'/source.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    report = {'schemaVersion': 1, 'classification': 'NATIVE_FRAME_TRANSFER_NOT_FIELD_VALIDATION',
        'rankingEligible': False, 'publicTerrain': terrain, 'coupled': cases,
        'frameIntervalPhysicsExact': True,
        'sourceCode': {str(p.relative_to(ROOT)): sha(p) for p in sources},
        'limitations': ['공개 DEM 사례의 외곽 경계·조도·초기 수심은 기존 진단 조건이며 서울 침수 예측 아님',
            '결합 사례는 합성 관망; 서울 실제 관망으로 표시하지 않음',
            '프레임은 기록 시각의 중심 수심·운동량이며 내부 단계 원 지표와 별도',
            '기관/소유권이 검증되는 서버 전달과 공통 게임 지도 렌더링 연결은 후속 범위']}
    write(directory/'summary.json', report)
    files = {str(p.relative_to(directory)): sha(p) for p in sorted(directory.rglob('*')) if p.is_file()}
    write(directory/'artifact-manifest.json', {'schemaVersion': 1, 'files': files})
    print(json.dumps({'files':len(files), 'manifestSha256':sha(directory/'artifact-manifest.json')}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
