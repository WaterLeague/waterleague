"""공개 서초 관망·분할 강우·지형의 실제 양방향 교환 검증."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'simulation'))
from waterleague_sim.engine.published_surface_connection import compile_connection, METHOD
from waterleague_sim.engine.coupled_flood import run_coupled
from waterleague_sim.engine.flood_errors import require


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2)+'\n')


def summarize(directories, output):
    from waterleague_sim.evaluation.coupled_adapter import read_coupled_record, engine_signature
    from waterleague_sim.evaluation.values import digest
    require(not output.exists() and len(directories) >= 2
            and len(set(directories)) == len(directories), 'CONNECTION_SUMMARY_INVALID')
    output.mkdir(parents=True)
    cases, depths, parameters = {}, {}, {}
    for directory in directories:
        result = json.loads((directory/'coupled-result.json').read_bytes())
        model = json.loads((directory/'coupled-input.json').read_bytes())
        network = json.loads((directory/'network/network-result.json').read_bytes())
        surface = json.loads((directory/'surface/surface-result.json').read_bytes())
        binding = model['publishedSurfaceConnection']
        context = {'scopeId': 'seocho-published-v3-public-terrain-window', 'modelGrade': 'EXPLORATORY',
            'evidenceClass': 'PUBLIC_DATA', 'comparisonKind': 'PAST_RAINFALL_STRESS_TEST',
            'effectAreaId': 'published-303ha-rectangle-not-damage-map',
            'scenarioSnapshotSha256': digest({k:v for k,v in binding['request'].items() if k != 'parameters'}),
            'forcingSha256': digest({'network': binding['summary']['originalNetworkSha256'],
                                    'surfaceRainfall': model['surfaceRainfall']}),
            'engineSha256': engine_signature(network, surface, result),
            'metricSpecificationSha256': digest(model['evaluationMetrics'])}
        record = read_coupled_record(directory, sha(directory/'coupled-result.json'), context)
        require(result['codeSha256'] == sha(ROOT/'simulation/waterleague_sim/engine/coupled_flood.py')
                and surface['engine']['exchangeAdapterSha256'] == sha(ROOT/'simulation/waterleague_sim/engine/surface_exchange.py')
                and surface['engine']['exchangeAccumulationSha256'] == sha(ROOT/'simulation/waterleague_sim/engine/accumulation.py'),
                'CONNECTION_EXECUTED_CODE_CHANGED')
        name = directory.name
        parameters[name] = binding['summary']['parameters']
        depths[name] = surface['final']['depthM']
        cases[name] = {'path': str(directory.relative_to(ROOT)), 'resultSha256': sha(directory/'coupled-result.json'),
            'verifiedFiles': len(result['files']), 'record': record, 'parameters': parameters[name],
            'durationSeconds': result['durationSeconds'], 'steps': result['steps'],
            'nativeDurationSeconds': network['durationSeconds'],
            'calendarDurationSeconds': network['calendarDurationSeconds'],
            'nativeCalendarShortfallSeconds': network['calendarShortfallSeconds'],
            'smallestExchangeMilliseconds': result['smallestExchangeMilliseconds'],
            'balance': result['balance'], 'networkConvergence': result['networkConvergence'],
            'networkQuality': result['networkNumericalQuality'],
            'surfaceQuality': result['surfaceNumericalQuality'],
            'maximumFinalDepthM': max(depths[name]),
            'sourceConnection': binding['summary']}
    first = next(iter(cases))
    comparisons = {}
    for name in list(cases)[1:]:
        require(cases[first]['record']['context'] == cases[name]['record']['context']
                and len(depths[first]) == len(depths[name]), 'CONNECTION_COMPARISON_CONTEXT_MISMATCH')
        differences = {k: {'reference':parameters[first][k], 'candidate':parameters[name][k]}
                       for k in parameters[first] if parameters[first][k] != parameters[name][k]}
        require(set(differences) == {'maximumExchangeMilliseconds'}, 'CONNECTION_COMPARISON_PARAMETERS_MISMATCH')
        comparisons[name] = {'reference': first, 'changedParameters': differences,
            'maximumAbsoluteFinalDepthDifferenceM': max(abs(a-b) for a,b in zip(depths[first],depths[name],strict=True)),
            'rawMetricCandidateMinusReference': {k: cases[name]['record']['raw'][k]-v
                                                 for k,v in cases[first]['record']['raw'].items()},
            'surfaceStorageDifferenceM3': cases[name]['balance']['surfaceStorageM3']-cases[first]['balance']['surfaceStorageM3']}
    sources = [Path(__file__), ROOT/'scripts/render_seocho_connection.py',
               *sorted((ROOT/'simulation/waterleague_sim').rglob('*.py'))]
    for path in sources:
        target = output/'source'/path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    report = {'schemaVersion': 1, 'method': METHOD, 'rankingEligible': False,
        'cases': cases, 'comparisons': comparisons,
        'reference': {'path': 'data/manifests/published-surface-connection-reference-v1.json',
                      'sha256': sha(ROOT/'data/manifests/published-surface-connection-reference-v1.json')},
        'verificationSource': {str(p.relative_to(ROOT)):sha(p) for p in sources},
        'limitations': ['미확인 공통 높이 기준·0.6m 등가 개구부·폐쇄 외곽 경계 가정',
            '원 시간대/관측소 미확인 강우와 추정 외부 유입 보존',
            '최종 수심 차이이며 전 시각 최대 차이/현장 오차가 아님',
            '원 달력 창·실제 엔진 기간·평가 창을 구분하며 당시 재해 복원이 아님',
            '지형 격자·기준고·개구부·조도·침투/증발·건물 피복과 게임 통합의 추가 검증 필요']}
    write(output/'report.json', report)
    write(output/'manifest.json', {'schemaVersion': 1, 'files': {
        str(p.relative_to(output)): sha(p) for p in sorted(output.rglob('*')) if p.is_file()}})
    print(json.dumps({'report': str(output/'report.json'), 'manifestSha256': sha(output/'manifest.json')}))


def request(partition, *, spacing=20, seconds=600, diameter=.6, coefficient=.62,
            offset=0., exchange=1000, boundary='REFLECTIVE', routing=.06):
    benchmark = json.loads((ROOT/'data/benchmarks/seocho-rainfall-partition-v1.json').read_bytes())
    require(sha(partition/'manifest.json') == benchmark['bundle']['manifestSha256'], 'CONNECTION_PARTITION_CHANGED')
    manifest = json.loads((partition/'manifest.json').read_bytes())
    paths = [f'surface-{spacing}m.json', f'coverage-{spacing}m.json', 'georeference.json',
             'terrain/original-network.inp']
    for name in paths:
        require(not (partition/name).is_symlink() and sha(partition/name) == manifest['files'][name],
                'CONNECTION_SOURCE_CHANGED')
    return {'schemaVersion': 1, 'method': METHOD,
        'sourceNetworkText': (partition/paths[3]).read_bytes().decode(),
        'sourceSurface': json.loads((partition/paths[0]).read_bytes()),
        'sourceLocation': json.loads((partition/paths[2]).read_bytes()),
        'sourceCoverage': json.loads((partition/paths[1]).read_bytes()),
        'parameters': {'openingDiameterM': diameter, 'dischargeCoefficient': coefficient,
            'surchargeHeadM': 100., 'surfaceOffsetM': offset, 'boundaryType': boundary,
            'durationSeconds': seconds, 'maximumExchangeMilliseconds': exchange,
            'frameIntervalMilliseconds': min(60000, seconds*1000),
            'networkNumericalProfile': {'id': 'seocho-slot-explicit', 'options': {
                'SURCHARGE_METHOD': 'SLOT', 'ROUTING_STEP': routing, 'MINIMUM_STEP': .01, 'MAX_TRIALS': 200}}},
        'evidence': '원 공개 관망·공개 지형·원 강우/추정 외부 유입 보존; 높이 기준 일치와 등가 원형 개구부는 가정'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--partition', type=Path)
    parser.add_argument('--summarize', type=Path, nargs='+')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seconds', type=int, default=600)
    parser.add_argument('--spacing', type=int, choices=(10, 20), default=20)
    parser.add_argument('--diameter', type=float, default=.6)
    parser.add_argument('--coefficient', type=float, default=.62)
    parser.add_argument('--offset', type=float, default=0.)
    parser.add_argument('--exchange', type=int, default=1000)
    parser.add_argument('--routing', type=float, default=.06)
    parser.add_argument('--boundary', choices=('REFLECTIVE', 'TRANSMISSIVE'), default='REFLECTIVE')
    args = parser.parse_args()
    if args.summarize:
        summarize([p.resolve() for p in args.summarize], args.output.resolve())
        return
    require(args.partition is not None, 'CONNECTION_PARTITION_REQUIRED')
    require(not args.output.exists(), 'CONNECTION_OUTPUT_EXISTS')
    model = compile_connection(request(args.partition, spacing=args.spacing, seconds=args.seconds,
        diameter=args.diameter, coefficient=args.coefficient, offset=args.offset,
        exchange=args.exchange, boundary=args.boundary, routing=args.routing))
    print(json.dumps({'ports': len(model['ports']), 'durationSeconds': args.seconds,
                      'output': str(args.output)}), flush=True)
    result = run_coupled(model, args.output)
    compact = {key: value for key, value in result.items() if key not in ('files', 'evaluationMetrics')}
    compact['metrics'] = result['evaluationMetrics']['raw']
    write(args.output/'summary.json', compact)
    print(json.dumps({'status': result['numericalStatus'], 'steps': result['steps'],
                      'balance': result['balance'], 'metrics': compact['metrics']}), flush=True)


if __name__ == '__main__':
    main()
