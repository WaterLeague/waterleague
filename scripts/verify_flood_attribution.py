"""실제 연결 엔진의 네 설계 조합으로 효과·표본 기여·재생 확인."""
from copy import deepcopy
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'simulation'))

from waterleague_sim.engine.coupled_flood import run_coupled
from waterleague_sim.reference.flood_cases import coupled_conduit_surcharge_case
from waterleague_sim.evaluation.attribution import attribute
from waterleague_sim.evaluation.coupled_adapter import engine_signature, file_digest, read_coupled_record
from waterleague_sim.evaluation.exception import require
from waterleague_sim.evaluation.service import METRICS, compare
from waterleague_sim.evaluation.values import canonical, digest


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    output = parser.parse_args().output.resolve()
    require(not output.exists(), 'BENCHMARK_OUTPUT_EXISTS')
    output.mkdir(parents=True)
    model = coupled_conduit_surcharge_case()
    members = [
        {'memberId': 'numerical-a', 'districtCode': '11110', 'facilityIds': ['numerical-storage-expansion']},
        {'memberId': 'numerical-b', 'districtCode': '11200', 'facilityIds': ['numerical-pipe-expansion']},
    ]
    experiment = {'classification': 'NUMERICAL_TEST_ONLY_NOT_REAL_INSTALLATIONS', 'baseline': model,
        'members': members, 'interventions': {
            'numerical-a': {'original': 'FUNCTIONAL 0 0 1', 'replacement': 'FUNCTIONAL 0 0 2',
                            'description': '합성 저장조 수면적 1→2m²'},
            'numerical-b': {'original': 'P0 CIRCULAR .15', 'replacement': 'P0 CIRCULAR .18',
                            'description': '합성 관로 직경 0.15→0.18m'}},
        'effectReferences': {'outwardVolumeM3': '3', 'peakOutwardM3s': '.1', 'depthAreaTimeM3Hours': '.01'},
        'referenceEvidence': '수치 검사 전용 기준량이며 서울 시즌 정책 아님'}
    save(output / 'experiment.json', experiment)
    results, directories = {}, {}
    for selected in ((), ('numerical-a',), ('numerical-b',), ('numerical-a', 'numerical-b')):
        changed = deepcopy(model)
        for member in selected:
            action = experiment['interventions'][member]
            require(changed['network']['inputText'].count(action['original']) == 1, 'NUMERICAL_DESIGN_MISMATCH')
            changed['network']['inputText'] = changed['network']['inputText'].replace(action['original'], action['replacement'])
        name = '+'.join(selected) or 'baseline'
        directory = output / name
        results[selected] = run_coupled(changed, directory)
        directories[selected] = directory
        print(name, results[selected]['numericalStatus'], results[selected]['evaluationMetrics']['raw'], flush=True)
    baseline = directories[()]
    network = json.loads((baseline / 'network/network-result.json').read_text())
    surface = json.loads((baseline / 'surface/surface-result.json').read_text())
    context = {'scopeId': 'NUMERICAL_CONDUIT_ATTRIBUTION_v1', 'modelGrade': 'DRAFT',
        'evidenceClass': 'NUMERICAL_TEST_ONLY', 'comparisonKind': 'CURRENT', 'effectAreaId': 'REFERENCE_BASIN',
        'scenarioSnapshotSha256': digest(model),
        'forcingSha256': digest(model['network']['inputText'].split('[INFLOWS]', 1)[1]),
        'engineSha256': engine_signature(network, surface, results[()]),
        'metricSpecificationSha256': results[()]['evaluationMetrics']['specificationSha256']}
    refs = experiment['effectReferences']
    policy = {'schemaVersion': 1, 'policyVersion': 'NUMERICAL_CONDUIT_EFFECTS_v1', 'context': context,
        'requiredMetrics': list(refs), 'metrics': {key: {'unit': METRICS[key][0], 'reference': value,
            'weight': '.6' if key == 'depthAreaTimeM3Hours' else '.2',
            'evidenceSha256': [file_digest(output / 'experiment.json')]} for key, value in refs.items()}}
    save(output / 'policy.json', policy)
    records = {selected: read_coupled_record(path, file_digest(path / 'coupled-result.json'), context)
               for selected, path in directories.items()}
    seen = []
    def evaluate(selected, facilities):
        expected = tuple(sorted(f for row in members if row['memberId'] in selected for f in row['facilityIds']))
        require(facilities == expected, 'NUMERICAL_MEMBER_BUNDLE_MISMATCH')
        seen.append(selected)
        return records[selected]
    cache = {}
    result = attribute(policy, members, evaluate, seed='b' * 64, samples=256, max_evaluations=4, cache=cache)
    save(output / 'attribution.json', result)
    save(output / 'coalition-cache.json', cache)
    # 보관된 원 결과·동일 seed로 재생하며 솔버를 다시 호출하지 않는다.
    def reject(*_):
        raise RuntimeError('재생에서 새 계산 호출 금지')
    replay = attribute(policy, members, reject, seed='b' * 64, samples=256, max_evaluations=0,
                       cache=json.loads((output / 'coalition-cache.json').read_text()))
    for key in ('status', 'memberEstimates', 'districtEstimates', 'conservation', 'permutations', 'coalitionEvaluations'):
        require(canonical(result[key]) == canonical(replay[key]), 'ATTRIBUTION_REPLAY_MISMATCH')
    require(replay['newEvaluations'] == 0, 'ATTRIBUTION_REPLAY_RECALCULATED')
    save(output / 'replay.json', replay)
    paths = [Path(__file__), ROOT / 'simulation/waterleague_sim/reference/flood_cases.py',
        *[ROOT / 'simulation/waterleague_sim/engine' / (name + '.py') for name in (
            'network', 'network_quality', 'network_exchange', 'network_metrics', 'coupled_flood',
            'flood_errors', 'flood_process', 'flood_metrics', 'surface', 'surface_exchange', 'swmm')],
        *sorted((ROOT / 'simulation/waterleague_sim/evaluation').glob('*.py')),
        ROOT / 'scripts/build_network_swmm.py', ROOT / 'scripts/build_live_swmm.py',
        *sorted((ROOT / 'simulation/native').glob('network_*.inc')),
        ROOT / 'simulation/uv.lock', ROOT / 'simulation/pyproject.toml', ROOT / 'data/manifests/anuga-4.0.1.json']
    for path in paths:
        target = output / 'source' / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    summary = {'schemaVersion': 1, 'classification': 'NUMERICAL_EVIDENCE_NOT_SEOUL_VALIDATION',
        'status': result['status'], 'requestedPermutations': 256, 'completedPermutations': result['completedPermutations'],
        'actualEngineRuns': len(results), 'coalitionEvaluationCalls': len(seen), 'replayNewEvaluations': 0,
        'policySha256': digest(policy), 'memberEstimates': result['memberEstimates'],
        'districtEstimates': result['districtEstimates'], 'conservation': result['conservation'],
        'wholeGroupComparison': compare(policy, records[()], records[('numerical-a', 'numerical-b')]),
        'limitations': ['합성 설계 조합·기준량이며 서울 자산·시즌 점수 정책 아님',
            '실제 공개 연결 유역·회원 소유권/동의·운영 순위 게시 연결 미완료',
            '표준오차는 순열 표본의 오차 추정이며 현장 정확도나 보장 신뢰구간 아님'],
        'files': {str(p.relative_to(output)): file_digest(p) for p in sorted(output.rglob('*')) if p.is_file()}}
    save(output / 'manifest.json', summary)
    print(result['status'], 'completed permutations', result['completedPermutations'], flush=True)


if __name__ == '__main__':
    main()
