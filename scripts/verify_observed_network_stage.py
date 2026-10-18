"""보관된 실제 수위·강우의 관망 및 지표 결합 입력 검증."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'simulation'))

from verify_observed_surface_rainfall import specification
from waterleague_sim.engine.coupled_flood import run_coupled
from waterleague_sim.engine.flood_errors import FloodModelError, require
from waterleague_sim.engine.flood_process import EngineProcess
from waterleague_sim.ingestion.wamis_stage import diagnostic_boundary, read_archive
from waterleague_sim.reference.flood_cases import tank_input, mesh, coupled_case


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + '\n')


def calendar(text):
    return text.replace('01/01/2020', '08/08/2022').replace('00:00:00', '09:00:00').replace('00:02:01', '10:00:01')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    directory = args.output.resolve()
    require(not directory.exists(), 'NETWORK_STAGE_OUTPUT_EXISTS')
    directory.mkdir(parents=True)
    manifest = ROOT / 'data/manifests/wamis-stage-1018662-20220725-20220820.json'
    normalized, files = read_archive(str(manifest.relative_to(ROOT)), sha(manifest))
    for name, raw in files.items():
        target = directory / 'observed-stage' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    start, end = '2022-08-08T09:00:00Z', '2022-08-08T10:00:00Z'
    boundary = diagnostic_boundary(normalized, start, end) | {'momentum': 'SWMM_DYNAMIC_WAVE'}
    model = {'inputText': calendar(tank_input(initial=.98).replace('TANK 0 ', 'TANK 2 ')
               .replace('OUT 0 FIXED 0 NO', 'OUT 2 FIXED 2.98 NO')),
        'verticalDatum': boundary['verticalDatum'], 'coordinateSystem': 'LOCAL_REFERENCE_METRES',
        'timeZone': 'UTC', 'startUtc': start, 'durationSeconds': 3600,
        'evidence': 'OBSERVED_GAUGE_ON_SYNTHETIC_NETWORK_NOT_SEOUL',
        'outfallStageBoundaries': {'OUT': boundary}}
    sources = [Path(__file__), ROOT / 'scripts/verify_observed_surface_rainfall.py',
               ROOT / 'simulation/uv.lock']
    for folder in ('forcing', 'ingestion', 'engine', 'reference'):
        sources.extend(sorted((ROOT / 'simulation/waterleague_sim' / folder).glob('*.py')))
    for source in sources:
        target = directory / 'source' / source.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    results, report = {}, {'schemaVersion': 1, 'rankingEligible': False,
        'classification': 'OBSERVED_GAUGE_ON_SYNTHETIC_NETWORK_AND_SURFACE',
        'sourceManifestSha256': sha(manifest), 'boundary': boundary, 'cases': [],
        'sourceCode': {str(p.relative_to(ROOT)): sha(p) for p in sources},
        'limitations': ['실제 관측 시계열의 합성 관망·지표 연결 검사; 서울 현장 제원 아님',
            '눈금 수위의 상대 기준 사용; 과거 영점표고·실제 서울 지형 결합 없음',
            '초기 물 상태와 시설 제원은 진단 조건; 선행 관측으로 복원된 현장 상태 아님']}
    for name, step, fixed in [('network-01s', .1, False), ('network-005s', .05, False),
                              ('network-replay-01s', .1, False), ('network-fixed-01s', .1, True)]:
        candidate = deepcopy(model)
        candidate['inputText'] = candidate['inputText'].replace('ROUTING_STEP 0.1', f'ROUTING_STEP {step}')
        if fixed:
            candidate.pop('outfallStageBoundaries')
        path = directory / name
        entry = {'name': name, 'maximumStepSeconds': step}
        last = None
        try:
            with EngineProcess('network', candidate, path, evaluation_seconds=3600) as session:
                with (path / 'frames.jsonl').open('x') as stream:
                    for _ in range(60):
                        last = session.call('advance', 60)
                        stream.write(json.dumps(last, allow_nan=False) + '\n')
                result = session.call('finish')
            results[name] = result
            entry.update(status=result['numericalStatus'], final=result['final'],
                quality=result['numericalQuality'], resultSha256=sha(path / 'network-result.json'))
        except FloodModelError as error:
            write(directory / (name + '-failure.json'), {'status': 'FAILED', 'code': str(error), 'lastState': last})
            entry.update(status='FAILED', code=str(error))
        report['cases'].append(entry)
        print(name, entry['status'], entry.get('final', {}).get('totals', entry.get('code')), flush=True)
    import numpy as np
    for name, exchange_ms in [('coupled-500ms', 500), ('coupled-250ms', 250)]:
        candidate = coupled_case(initial_network=.98, exchange_ms=exchange_ms)
        candidate.update(durationSeconds=3600, frameIntervalMilliseconds=60_000,
                         evidence='OBSERVED_GAUGE_AND_RAIN_ON_SYNTHETIC_COUPLED_DOMAIN')
        candidate['surface'] = mesh(2, 2, 10, 10, bed=lambda x, y: np.full(len(x), 3.1))
        candidate['surface'].update(schemaVersion=2, maxStepSeconds=.1, verticalDatum=boundary['verticalDatum'])
        inp = candidate['network']['inputText'].replace('TANK 0 ', 'TANK 2 ')
        inp = inp.replace('OUT 0 FIXED 0 NO', 'OUT 2 FIXED 2.98 NO').replace('SURFACE 1 FIXED 1 NO', 'SURFACE 3.1 FIXED 3.1 NO')
        inp = inp.replace('INLET TANK SURFACE BOTTOM 1 ', 'INLET TANK SURFACE BOTTOM 1.1 ')
        inp = inp.replace('FUNCTIONAL 0 0 1 ', 'FUNCTIONAL 0 0 10 ')
        candidate['network'] = model | {'inputText': calendar(inp)}
        candidate['ports'][0].update(crestM=3.1, surfaceTriangles=list(range(8)))
        candidate['observedRainfall'] = specification(candidate['surface'], minutes=60, two_stations=False)
        path = directory / name
        entry = {'name': name, 'maximumExchangeMilliseconds': exchange_ms}
        try:
            result = run_coupled(candidate, path)
            results[name] = result
            entry.update(status=result['numericalStatus'], balance=result['balance'],
                networkQuality=result['networkNumericalQuality'], surfaceQuality=result.get('surfaceNumericalQuality'),
                smallestExchangeMilliseconds=result['smallestExchangeMilliseconds'],
                resultSha256=sha(path / 'coupled-result.json'))
        except FloodModelError as error:
            entry.update(status='FAILED', code=str(error))
        report['cases'].append(entry)
        print(name, entry['status'], entry.get('balance', entry.get('code')), flush=True)
    if all(name in results for name in ('network-01s', 'network-005s', 'network-replay-01s', 'network-fixed-01s')):
        a, b = (results[name]['final'] for name in ('network-01s', 'network-005s'))
        report['networkComparison'] = {'exactReplay': a == results['network-replay-01s']['final'],
            'tankHeadDifferenceM': a['nodes']['TANK']['headM'] - b['nodes']['TANK']['headM'],
            'storageDifferenceM3': a['totals']['storageM3'] - b['totals']['storageM3'],
            'variableMinusFixedStorageM3': a['totals']['storageM3'] - results['network-fixed-01s']['final']['totals']['storageM3']}
    if all(name in results for name in ('coupled-500ms', 'coupled-250ms')):
        a, b = (results[name]['balance'] for name in ('coupled-500ms', 'coupled-250ms'))
        report['coupledComparison'] = {key: a[key] - b[key] for key in
            ('surfaceStorageM3', 'networkStorageM3', 'networkToSurfaceM3', 'surfaceToNetworkM3')}
    write(directory / 'summary.json', report)
    write(directory / 'artifact-manifest.json', {'schemaVersion': 1, 'files': {
        str(p.relative_to(directory)): sha(p) for p in sorted(directory.rglob('*')) if p.is_file()}})
    print(json.dumps({'manifestSha256': sha(directory / 'artifact-manifest.json'),
                      'networkComparison': report.get('networkComparison'),
                      'coupledComparison': report.get('coupledComparison')}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
