"""고정 매니페스트와 보관 코드로 결합 계산을 독립 재생."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import sys
import tempfile


def sha(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''): value.update(block)
    return value.hexdigest()


def require(value, code):
    if not value: raise ValueError(code)


def load(path):
    require(path.stat().st_size <= 64*1024*1024, 'REPLAY_ARTIFACT_TOO_LARGE')
    def pairs(items):
        value = {}
        for key, item in items:
            require(key not in value, 'REPLAY_DUPLICATE_KEY')
            value[key] = item
        return value
    def reject(_):
        raise ValueError('REPLAY_NONFINITE_VALUE')
    return json.loads(path.read_bytes(), object_pairs_hook=pairs, parse_constant=reject)


def safe_path(root, name):
    relative = PurePosixPath(name)
    require(not relative.is_absolute() and '..' not in relative.parts and relative.parts,
            'REPLAY_PATH_INVALID')
    path = root/relative
    require(path.resolve().is_relative_to(root) and not any((root/Path(*relative.parts[:i])).is_symlink()
            for i in range(1, len(relative.parts)+1)), 'REPLAY_PATH_INVALID')
    return path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--manifest-sha256', required=True)
    parser.add_argument('--case', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--kind', choices=('coupled', 'inlet-network', 'refined-inlet-network'), default='coupled')
    args = parser.parse_args()
    bundle = args.bundle.resolve()
    manifest = safe_path(bundle, 'manifest.json')
    require(re.fullmatch('[a-f0-9]{64}', args.manifest_sha256)
        and sha(manifest) == args.manifest_sha256, 'REPLAY_MANIFEST_HASH_MISMATCH')
    files = load(manifest)['files']
    require(isinstance(files, dict) and 0 < len(files) <= 100_000, 'REPLAY_MANIFEST_INVALID')
    for name, expected in files.items():
        path = safe_path(bundle, name)
        require(isinstance(expected, str) and re.fullmatch('[a-f0-9]{64}', expected)
                and path.is_file() and sha(path) == expected, 'REPLAY_ARTIFACT_HASH_MISMATCH')
    case = safe_path(bundle, args.case)
    required = ('coupled-input.json', 'coupled-result.json', 'network/network.out') if args.kind == 'coupled' else (
        'original.inp', 'design.json', 'transformation.json', 'network/network-result.json',
        'network/network.inp', 'network/network.out')
    if args.kind == 'refined-inlet-network':
        required += ('refinement.json', 'numerical-profile.json', 'prepared.inp', 'experiment-result.json')
    require(all(str((case/name).relative_to(bundle)) in files for name in required), 'REPLAY_CASE_MISSING')
    if args.kind == 'coupled' and 'initialization' in load(case/'coupled-result.json'):
        require(all(str((case/name).relative_to(bundle)) in files for name in
            ('evaluation-initial-state.json', 'evaluation-final-state.json')), 'REPLAY_CASE_MISSING')
    if args.kind == 'coupled' and 'connectedCistern' in load(case/'coupled-result.json'):
        require(all(str((case/name).relative_to(bundle)) in files for name in
            ('connected-cistern-design.json', 'cistern-network.inp',
             'cistern-evaluation-initial.json', 'cistern-evaluation-final.json')), 'REPLAY_CASE_MISSING')
    output = args.output.resolve()
    require(not output.exists() and not output.is_relative_to(bundle), 'REPLAY_OUTPUT_INVALID')
    require('source/simulation/waterleague_sim/engine/coupled_flood.py' in files, 'REPLAY_SOURCE_MISSING')
    with tempfile.TemporaryDirectory(prefix='waterleague-replay-') as temporary:
        source = (Path(temporary)/'source').resolve()
        for name, expected in files.items():
            if not name.startswith('source/'): continue
            target = Path(temporary)/name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(safe_path(bundle, name), target)
            require(sha(target) == expected, 'REPLAY_SOURCE_COPY_MISMATCH')
        replay(source, case, output, args)


def replay(source, case, output, args):
    # 검증 전에는 보관 Python을 가져오지 않으며 자식 엔진도 같은 경로를 상속한다.
    # 검증 목록만 복사하여 원 묶음에 추가된 모듈·바이트코드를 실행하지 않는다.
    sys.path[:0] = [str(source/'simulation'), str(source)]
    from waterleague_sim.engine import network
    require(network.ROOT == source, 'REPLAY_SOURCE_ROOT_MISMATCH')
    experiment_comparisons = {}
    if args.kind in ('inlet-network', 'refined-inlet-network'):
        from waterleague_sim.engine.connected_inlets import compile_inlets
        from waterleague_sim.engine.flood_process import EngineProcess
        if args.kind == 'refined-inlet-network':
            from waterleague_sim.engine.inlet_experiment import prepare, run
            inputs = ((case/'original.inp').read_bytes(), load(case/'design.json'),
                      load(case/'refinement.json'), load(case/'numerical-profile.json'))
            raw, transformation = prepare(*inputs)
            require(raw == (case/'prepared.inp').read_bytes(), 'REPLAY_INLET_INPUT_MISMATCH')
        else:
            raw, transformation = compile_inlets((case/'original.inp').read_bytes(), load(case/'design.json'))
        require(transformation == load(case/'transformation.json')
            and raw == (case/'network/network.inp').read_bytes(), 'REPLAY_INLET_INPUT_MISMATCH')
        expected = load(case/'network/network-result.json')
        if args.kind == 'refined-inlet-network':
            recorded = load(case/'experiment-result.json')
            require(recorded['nativeResultSha256'] == sha(case/'network/network-result.json'),
                    'REPLAY_EXPERIMENT_BINDING_INVALID')
            experiment, actual = run(*inputs, output)
            experiment_comparisons = {name: recorded.get(name) == experiment.get(name) for name in (
                'schemaVersion', 'classification', 'rankingEligible', 'transformationSha256',
                'codeSha256', 'virtualNodes', 'nativeNumericalStatus', 'numericalStatus', 'failureReasons')}
        else:
            output.mkdir(parents=True)
            with EngineProcess('inlet_network', raw.decode(), output/'network', native_duration=True) as process:
                actual = process.call('run', 60)['result']
        fields = ('numericalStatus', 'numericalQuality', 'convergence', 'initial', 'final',
                  'evaluationMetrics', 'inletOperation', 'numericalConfiguration')
    else:
        from waterleague_sim.engine.coupled_flood import run_coupled
        expected = load(case/'coupled-result.json')
        actual = run_coupled(load(case/'coupled-input.json'), output)
        fields = ('numericalStatus', 'balance', 'evaluationMetrics', 'connectedPumps',
            'connectedStorage', 'connectedCistern', 'surfaceBasins', 'connectedFacilities', 'initialization', 'networkNumericalProfile',
            'networkRainfall', 'observedRainfall')
    comparisons = {name: expected.get(name) == actual.get(name) for name in fields}
    native = ['network/network.out']
    if 'networkRainfall' in expected:
        native += ['rainfall-network.inp', 'network/network.inp', 'network-frames.jsonl']
        native += [name for name in expected['files'] if name.startswith('surface/native-frames/')
                   or 'ledger' in name]
        for component in ('network', 'surface'):
            original_engine = load(case/component/(component+'-result.json'))['engine']
            replay_engine = load(output/component/(component+'-result.json'))['engine']
            comparisons[component+'EngineIdentity'] = original_engine == replay_engine
    if 'initialization' in expected:
        native += ['evaluation-initial-state.json', 'evaluation-final-state.json']
    if 'connectedCistern' in expected:
        native += ['connected-cistern-design.json', 'cistern-network.inp',
                   'cistern-evaluation-initial.json', 'cistern-evaluation-final.json']
    native_hashes = {name: {'expected': sha(safe_path(case, name)),
                            'actual': sha(safe_path(output, name))} for name in native}
    matched = all(comparisons.values()) and all(experiment_comparisons.values()) and all(
        row['expected'] == row['actual'] for row in native_hashes.values())
    report = {'schemaVersion': 1, 'status': 'MATCHED' if matched else 'DIFFERENT',
        'source': 'VERIFIED_ARCHIVED_CODE_BINARY_FORCING_ONLY', 'sourceManifestSha256': args.manifest_sha256,
        'case': args.case, 'originalNumericalStatus': expected['numericalStatus'],
        'replayedNumericalStatus': actual['numericalStatus'], 'fields': comparisons, 'files': native_hashes}
    if experiment_comparisons:
        report.update({'experimentFields': experiment_comparisons,
            'originalExperimentStatus': recorded['numericalStatus'],
            'replayedExperimentStatus': experiment['numericalStatus']})
    (output/'replay-verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(report, ensure_ascii=False), flush=True)
    require(matched, 'REPLAY_RESULT_MISMATCH')


if __name__ == '__main__': main()
