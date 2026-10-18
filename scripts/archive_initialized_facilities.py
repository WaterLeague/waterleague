"""선행 관측 시설 계산의 원문·코드·엔진 보존과 같은 입력 재생."""
import argparse
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'simulation'))
from waterleague_sim.engine import facility_metrics
from waterleague_sim.engine.connected_facilities import CATALOG_PATH
from waterleague_sim.engine.flood_errors import require
from waterleague_sim.engine.initialized_facilities import run_initialized_facilities
from waterleague_sim.engine.network import sha256


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2)+'\n')


def archive(directory):
    directory = directory.resolve()
    require(directory.is_relative_to(ROOT/'data/runs') and directory.is_dir()
        and not (directory/'manifest.json').exists() and not (directory/'source').exists(),
        'INITIALIZED_ARCHIVE_DIRECTORY_INVALID')
    require(not any(p.is_symlink() for p in directory.rglob('*')), 'INITIALIZED_ARCHIVE_SYMLINK')
    reports = sorted(directory.glob('*/initialized-facilities-result.json'))
    require(reports, 'INITIALIZED_ARCHIVE_RESULTS_REQUIRED')
    summaries = {}
    for path in reports:
        result = json.loads(path.read_bytes())
        require(result['schemaVersion'] == 2 and result['engine'] == facility_metrics.identity()
            and result['adapterSha256'] == sha256(ROOT/'simulation/waterleague_sim/engine/initialized_facilities.py'),
            'INITIALIZED_ARCHIVE_CODE_CHANGED')
        for name, expected in result['files'].items():
            original = path.parent/name
            require(not Path(name).is_absolute() and '..' not in Path(name).parts
                and original.is_file() and sha256(original) == expected, 'INITIALIZED_ARCHIVE_FILE_CHANGED')
        summaries[path.parent.name] = {
            'numericalStatus': result['numericalStatus'], 'window': result['evaluationLedger']['outfallMetrics'],
            'warmupSeconds': result['initialization']['warmupSeconds'],
            'evaluationInitialFacilities': result['evaluationInitialFacilities'],
            'routingBalance': result['evaluationLedger']['routingBalance']}
    paths = [*list((ROOT/'simulation/waterleague_sim').rglob('*.py')),
        *list((ROOT/'simulation/native').glob('*.inc')), CATALOG_PATH, Path(__file__),
        ROOT/'scripts/build_facility_metrics_swmm.py', ROOT/'scripts/build_live_swmm.py',
        ROOT/'scripts/build_facility_swmm.py', ROOT/'scripts/build_network_swmm.py',
        ROOT/'simulation/pyproject.toml', ROOT/'simulation/uv.lock', ROOT/'tmp/swmm/source.tar.gz',
        facility_metrics.library_path(), facility_metrics.library_path().parent/'network-build.json']
    for path in paths:
        target = directory/'source'/path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    for result in reports:
        for path in (result.parent/'observations/data').rglob('*'):
            if not path.is_file(): continue
            target = directory/'source/data'/path.relative_to(result.parent/'observations/data')
            require(not target.exists() or sha256(target) == sha256(path), 'INITIALIZED_ARCHIVE_SOURCE_CONFLICT')
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
    write(directory/'outfall-summary.json', {'classification': 'OBSERVED_WEATHER_SYNTHETIC_NETWORK',
        'rankingEligible': False, 'cases': summaries})
    files = {str(p.relative_to(directory)): sha256(p) for p in sorted(directory.rglob('*')) if p.is_file()}
    write(directory/'manifest.json', {'schemaVersion': 1, 'files': files})
    print(json.dumps({'files': len(files), 'manifestSha256': sha256(directory/'manifest.json')}))


def replay(directory, case, output):
    manifest = json.loads((directory/'manifest.json').read_bytes())
    require(directory.resolve()/'source' == ROOT and isinstance(case, str)
        and case in json.loads((directory/'outfall-summary.json').read_bytes())['cases'],
        'INITIALIZED_REPLAY_ARCHIVED_SOURCE_REQUIRED')
    for name, expected in manifest['files'].items():
        path = directory/name
        require(not Path(name).is_absolute() and '..' not in Path(name).parts and not path.is_symlink()
            and path.is_file() and sha256(path) == expected, 'INITIALIZED_REPLAY_FILE_CHANGED')
    source = directory/case
    request = json.loads((source/'request.json').read_bytes())
    result = run_initialized_facilities(request['network'], request['observation'],
        request['initialization'], request['design'], output)
    expected = json.loads((source/'initialized-facilities-result.json').read_bytes())
    require(result['evaluationLedger'] == expected['evaluationLedger']
        and result['evaluationInitialFacilities'] == expected['evaluationInitialFacilities']
        and result['evaluationFinalFacilities'] == expected['evaluationFinalFacilities']
        and sha256(output/'network/network.out') == sha256(source/'network/network.out'),
        'INITIALIZED_REPLAY_DIFFERENT')
    print(json.dumps({'case': case, 'nativeOutEqual': True, 'metricsEqual': True, 'statesEqual': True}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('--replay-case')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.replay_case:
        require(args.output is not None, 'INITIALIZED_REPLAY_OUTPUT_REQUIRED')
        replay(args.directory.resolve(), args.replay_case, args.output.resolve())
    else:
        require(args.output is None, 'INITIALIZED_ARCHIVE_ARGUMENT_INVALID')
        archive(args.directory)
