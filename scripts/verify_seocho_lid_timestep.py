"""같은 공개 사건·세 시설에서 수문 간격만 바꾼 원 엔진 비교."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'simulation'))
from waterleague_sim.engine.flood_errors import require
from waterleague_sim.engine.flood_process import EngineProcess
from waterleague_sim.ingestion.network_variant import derive_compiled, hydraulic_input_hash
from waterleague_sim.ingestion.published_network import records
from waterleague_sim.run_watershed_job import inputs, CATALOG_HASH

STEPS = (300, 60, 10, 2, 1)
FIXTURE = ROOT/'simulation/tests/fixtures/seocho-three-lid-design-v1.json'


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def pair():
    raw = FIXTURE.read_text()
    request = {'modelHash': CATALOG_HASH, 'placements': raw,
        'inputHash': hashlib.sha256((CATALOG_HASH+'\n'+raw).encode()).hexdigest()}
    values = inputs(request)
    return dict(zip(('baseline', 'strategy'), values[2:4]))


def run(output):
    require(not output.exists(), 'TIMESTEP_OUTPUT_EXISTS')
    output.mkdir(parents=True)
    source = pair()
    for step in STEPS:
        for name, raw in source.items():
            changed, _ = derive_compiled(raw, {'id': f'hydrology-{step}s',
                'options': {'WET_STEP': step, 'DRY_STEP': step}})
            with EngineProcess('facility_metrics', changed.decode(), output/f'{step}-{name}',
                               native_duration=True) as engine:
                engine.call('run', 300)
    return summarize([output])


def summarize(directories):
    source = pair()
    cases = []
    engines = []
    def fixed_tokens(raw):
        return {name: [row['tokens'] for row in rows if name != 'OPTIONS'
                      or row['tokens'][0] not in ('WET_STEP', 'DRY_STEP')]
                for name, rows in records(raw)[1].items()}
    for step in STEPS:
        for name in source:
            matches = [root/f'{step}-{name}' for root in directories if (root/f'{step}-{name}').is_dir()]
            require(len(matches) == 1, 'TIMESTEP_CASE_MISSING_OR_DUPLICATE')
            path = matches[0]
            result = json.loads((path/'network-result.json').read_bytes())
            raw = (path/'network.inp').read_bytes()
            expected = f'{step//3600:02}:{step//60%60:02}:{step%60:02}'
            options = {r['tokens'][0]: r['tokens'][1] for r in records(raw)[1]['OPTIONS']}
            require(options['WET_STEP'] == options['DRY_STEP'] == expected
                    and fixed_tokens(raw) == fixed_tokens(source[name])
                    and hydraulic_input_hash(raw, hydrology=True) == hydraulic_input_hash(source[name], hydrology=True),
                    'TIMESTEP_PHYSICAL_INPUT_CHANGED')
            require(set(result['files']) == {'network.inp', 'network.rpt', 'network.out', 'network-frames.jsonl'},
                    'TIMESTEP_ARTIFACT_MISSING')
            for filename, expected_hash in result['files'].items():
                require(filename in ('network.inp', 'network.rpt', 'network.out', 'network-frames.jsonl')
                        and sha(path/filename) == expected_hash, 'TIMESTEP_ARTIFACT_CHANGED')
            require(result['complete'] and result['durationSeconds'] == 86339
                    and result['convergence']['nonConvergedSteps'] == 0, 'TIMESTEP_INCOMPLETE')
            require(result['numericalStatus'] == ('FAILED' if step == 300 and name == 'strategy' else 'PASSED'),
                    'TIMESTEP_EXPECTED_STATUS_CHANGED')
            engines.append(result['engine'])
            cases.append({'stepSeconds': step, 'case': name, 'path': str(path.relative_to(ROOT)),
                'resultSha256': sha(path/'network-result.json'), 'verifiedFiles': result['files'],
                'physicalInputSha256': hydraulic_input_hash(raw, hydrology=True),
                'durationSeconds': result['durationSeconds'], 'numericalStatus': result['numericalStatus'],
                'runoffContinuityPercent': result['runoffContinuityPercent'],
                'routingContinuityPercent': result['routingContinuityPercent'],
                'convergence': result['convergence'], 'facilities': result['final']['facilities'],
                'raw': {k: result['evaluationMetrics']['combined'][k] for k in ('outwardVolumeM3', 'peakOutwardM3s')}})
    a = next(c for c in cases if c['stepSeconds'] == 2 and c['case'] == 'strategy')
    b = next(c for c in cases if c['stepSeconds'] == 1 and c['case'] == 'strategy')
    by_id = {p['swmmId']: p for p in a['facilities']}
    fields = ('inflowM3', 'surfaceOutflowM3', 'drainOutflowM3', 'infiltrationM3', 'finalStorageM3')
    changes = {p['swmmId']: {k: p[k]-by_id[p['swmmId']][k] for k in fields} for p in b['facilities']}
    require(all(engine == engines[0] for engine in engines), 'TIMESTEP_ENGINE_CHANGED')
    return {'schemaVersion': 1, 'classification': 'NATIVE_PUBLIC_EVENT_HYDROLOGY_REFINEMENT',
        'sourceUrl': 'https://raw.githubusercontent.com/USEPA/Stormwater-Management-Model/v5.2.4/src/solver/lidproc.c',
        'sourceRevision': '7952ca837988b1c32f791812eccc9fd64547e093',
        'fixture': {'path': str(FIXTURE.relative_to(ROOT)), 'sha256': sha(FIXTURE)},
        'engine': engines[0], 'cases': cases, 'oneSecondMinusTwoSecondFacilityVolumesM3': changes,
        'physicalInputsUnchanged': True, 'continuityToleranceChanged': False,
        'rankingEligible': False, 'fieldAccuracyValidated': False,
        'limitations': ['원 공개 강우·추정 외부 유입의 관망 비교; 관측 피해 재현 아님',
            '1초와 2초의 체적 차이는 수치 민감도이며 현장 오차 추정치 아님',
            '다른 시설 수량·배치와 지표 결합 계산은 실행별 수지·수렴 검사 필요']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--run', type=Path)
    group.add_argument('--summarize', type=Path, nargs='+')
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    value = run(args.run.resolve()) if args.run else summarize([p.resolve() for p in args.summarize])
    args.report.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2)+'\n')
    print(json.dumps({'cases': len(value['cases']), 'physicalInputsUnchanged': True}))
