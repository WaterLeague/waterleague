"""결합 펌프 진단의 원 입력·실패·실행 코드·엔진 보관."""
import argparse
import json
from pathlib import Path
import platform
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'simulation'))

from analyze_coupled_initialization import archive_source
from waterleague_sim.engine import coupled_flood, coupled_pump_network, network_metrics, surface
from waterleague_sim.engine.connected_pumps import CATALOG
from waterleague_sim.engine.flood_errors import require
from waterleague_sim.evaluation.coupled_adapter import file_digest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--run', type=Path, action='append', required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    require(not output.exists(), 'PUMP_ARCHIVE_OUTPUT_EXISTS')
    runs = [p.resolve() for p in args.run]
    require(len({p.name for p in runs}) == len(runs)
        and all(p.is_dir() and p.is_relative_to(ROOT/'data/runs') and p != output for p in runs),
        'PUMP_ARCHIVE_INPUT_INVALID')
    records = {}
    for run in runs:
        for path in run.rglob('coupled-result.json'):
            result = json.loads(path.read_bytes())
            network = json.loads((path.parent/'network/network-result.json').read_bytes())
            terrain = json.loads((path.parent/'surface/surface-result.json').read_bytes())
            require(result['codeSha256'] == file_digest(coupled_flood.__file__), 'PUMP_ARCHIVE_SOURCE_CHANGED')
            if 'connectedPumps' in result:
                require(all(network['engine'].get(k) == v for k, v in coupled_pump_network.identity().items()),
                        'PUMP_ARCHIVE_ENGINE_CHANGED')
            require(all(terrain['engine'].get(k) == v for k, v in surface.identity().items()),
                    'PUMP_ARCHIVE_SURFACE_CHANGED')
            records[str(Path(run.name)/path.relative_to(run))] = file_digest(path)
    require(records, 'PUMP_ARCHIVE_NO_RESULT')
    output.mkdir(parents=True)
    sources = archive_source(output)
    extra = [CATALOG, *list((ROOT/'simulation/tests').glob('test_*pump*.py')),
             ROOT/'simulation/tests/test_storage_composition.py', ROOT/'simulation/tests/test_flood_attribution.py',
             ROOT/'simulation/tests/test_coupled_numerics.py', ROOT/'simulation/tests/test_network_variant.py',
             ROOT/'simulation/tests/test_replay_coupled_bundle.py']
    for binary in (coupled_pump_network.library_path(), network_metrics.library_path()):
        extra += [binary, *binary.parent.glob('*build.json')]
    for path in extra:
        target = output/'source'/path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        sources[str(path.relative_to(ROOT))] = file_digest(path)
    for run in runs:
        require(not any(p.is_symlink() for p in run.rglob('*')), 'PUMP_ARCHIVE_SYMLINK_INVALID')
        shutil.copytree(run, output/run.name)
        # 실행 묶음의 공개 입력을 원 경로로 복원하며 같은 경로의 다른 원문은 거부한다.
        for directory in (p for p in run.rglob('data') if p.is_dir()):
            for path in (p for p in directory.rglob('*') if p.is_file()):
                relative = Path('data')/path.relative_to(directory)
                target = output/'source'/relative
                require(not target.exists() or file_digest(target) == file_digest(path),
                        'PUMP_ARCHIVE_FORCING_CONFLICT')
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, target)
                sources[str(relative)] = file_digest(path)
    manifest = {'schemaVersion': 1, 'classification': 'NUMERICAL_DIAGNOSTIC_NOT_SEOUL_VALIDATION',
        'rankingEligible': False, 'runtime': {'python': platform.python_version(),
            'platform': platform.platform()}, 'resultHashes': records, 'sourceHashes': sources,
        'files': {str(p.relative_to(output)): file_digest(p) for p in sorted(output.rglob('*')) if p.is_file()}}
    (output/'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({'files': len(manifest['files']), 'manifestSha256': file_digest(output/'manifest.json')}))


if __name__ == '__main__': main()
