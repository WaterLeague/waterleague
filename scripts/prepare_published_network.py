"""해시 고정 공개 관망 원본의 가져오기와 격리된 진단 계산."""
import argparse
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'simulation'))

from waterleague_sim.engine.flood_errors import FloodModelError, require
from waterleague_sim.engine.flood_process import EngineProcess
from waterleague_sim.ingestion.published_network import digest, execution_input, load_archive


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + '\n')


def run_case(text, directory):
    with EngineProcess('network', text, directory / 'calculation', native_duration=True) as engine:
        duration = engine.info['evaluationSeconds']
        require(0 < duration <= 45 * 86400, 'PUBLISHED_DURATION_LIMIT_EXCEEDED')
        return engine.call('run', 300)['result']


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest', type=Path, default=ROOT / 'data/manifests/mendeley-seocho-network-v3.json')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--run', action='store_true')
    args = parser.parse_args()
    output = args.output.resolve()
    require(not output.exists(), 'PUBLISHED_OUTPUT_EXISTS')
    source, source_hash, inputs = load_archive(ROOT, args.manifest)
    output.mkdir(parents=True)
    shutil.copyfile(args.manifest, output / 'source-manifest.json')
    source_paths = [Path(__file__), ROOT / 'simulation/waterleague_sim/ingestion/published_network.py',
        *[ROOT / 'simulation/waterleague_sim/engine' / (name + '.py') for name in (
            'network', 'network_quality', 'flood_process', 'flood_errors', 'swmm')],
        ROOT / 'simulation/native/network_snapshot.inc', ROOT / 'scripts/build_network_swmm.py',
        ROOT / 'simulation/pyproject.toml', ROOT / 'simulation/uv.lock']
    for path in source_paths:
        target = output / 'source' / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    if args.run:
        from waterleague_sim.engine import network
        engine_identity = network.identity()
        (output / 'engine').mkdir()
        for path in (network.library_path(), network.library_path().parent / 'network-build.json'):
            shutil.copyfile(path, output / 'engine' / path.name)
    else:
        engine_identity = None
    cases = []
    for index, row in enumerate(inputs):
        name = f'case-{index:02d}'
        directory = output / name
        directory.mkdir()
        (directory / 'original.inp').write_bytes(row['raw'])
        write(directory / 'audit.json', row['audit'])
        case = {'id': name, 'member': row['member'], 'sourceSha256': row['audit']['sourceSha256'],
            'areaHa': row['audit']['areaHa'], 'counts': row['audit']['counts'],
            'rankingEligible': False, 'fieldValidated': False, 'executionStatus': 'NOT_REQUESTED'}
        try:
            text, transformations = execution_input(row['raw'])
            (directory / 'execution.inp').write_bytes(text.encode())
            write(directory / 'transformations.json', transformations)
            case['executionSha256'] = transformations['executionSha256']
            case['reportPathsDisabled'] = len(transformations['changes'])
            case['preservedNonfiniteTokenCount'] = len(transformations['preservedNonfiniteUnusedTokens'])
            if args.run:
                result = run_case(text, directory)
                case.update({'executionStatus': 'COMPLETED', 'numericalStatus': result['numericalStatus'],
                    'complete': result['complete'], 'convergence': result['convergence'],
                    'timeWindowPolicy': result['timeWindowPolicy'],
                    'calendarShortfallSeconds': result['calendarShortfallSeconds'],
                    'quality': result['numericalQuality'], 'totals': result['final']['totals'],
                    'warningCount': result['warningCount'],
                    'runoffContinuityPercent': result['runoffContinuityPercent'],
                    'routingContinuityPercent': result['routingContinuityPercent']})
        except FloodModelError as error:
            case.update({'executionStatus': 'REJECTED', 'failureCode': str(error)})
            write(directory / 'failure.json', case)
        cases.append(case)
        print(json.dumps({key: case[key] for key in ('id', 'executionStatus', 'numericalStatus', 'failureCode')
                          if key in case}), flush=True)
    summary = {'schemaVersion': 1, 'classification': source['classification'],
        'sourceManifestSha256': source_hash, 'sourceArchiveSha256': source['archive']['sha256'],
        'doi': source['doi'], 'attribution': source['attribution'], 'licence': source['licence'],
        'engine': engine_identity, 'rankingEligible': False, 'cases': cases,
        'limitations': source['limitations'] + ['전체 수렴·물수지 실패를 보존하며 발표 수치와 동일하다고 가정하지 않음',
            '각 300초 프레임은 표시용이며 내부 수렴·수지 판정은 모든 엔진 단계 기준'],
        'files': {str(path.relative_to(output)): digest(path.read_bytes())
                  for path in sorted(output.rglob('*')) if path.is_file()}}
    write(output / 'manifest.json', summary)
    print(json.dumps({'cases': len(cases), 'manifestSha256': digest((output / 'manifest.json').read_bytes())}), flush=True)


if __name__ == '__main__':
    main()
