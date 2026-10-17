"""CPU 탐색 원장 재생·출처 검증 및 선택적 실제 엔진 재계산."""
from pathlib import Path
from datetime import datetime
import argparse
import hashlib
import json
import math
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'simulation'))
from waterleague_sim.model_catalog import read_catalog
from waterleague_sim.reference.search import cost, key, search
from waterleague_sim.engine import swmm


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def close(a, b, tolerance=1e-7):
    return math.isfinite(a) and math.isfinite(b) and math.isclose(a, b, rel_tol=tolerance, abs_tol=tolerance)


def verify_family(report_name, ledger_name, runner, training_id, expected_ids, rerun=False, rerun_candidates=False):
    report_path = ROOT/'data/derived'/report_name
    ledger_path = ROOT/'data/derived'/ledger_name
    report = json.loads(report_path.read_text())
    ledger = json.loads(ledger_path.read_text())
    for p in (report_path, ledger_path):
        require(p.read_bytes() == (ROOT/'backend/src/main/resources/models'/p.name).read_bytes(), '서버 원문 불일치')
    require(report['schemaVersion'] == 1 and report['kind'] == 'CPU_REFERENCE' and report['official'] is False and report['validationLevel'] == 'EXPLORATORY' and report['currency'] == 'KRW', 'CPU 등급 계약 불일치')
    require(report['algorithm'] == 'GREEDY_MARGINAL_DISCHARGE_PER_KRW_V1' and report['stepAreaM2'] == 10, '탐색 계약 불일치')
    for field, filename in [('algorithmSha256', 'simulation/waterleague_sim/reference/search.py'), ('runnerSha256', runner), ('generatorSha256', 'simulation/waterleague_sim/engine/swmm.py'), ('ledgerSha256', 'data/derived/'+ledger_name)]:
        require(report[field] == digest(ROOT/filename), f'{field} 불일치')
    require(report['id'] == hashlib.sha256((report['trainingModelHash']+report['algorithmSha256']+report['runnerSha256']).encode()).hexdigest(), '기준안 식별자 불일치')
    require(datetime.fromisoformat(report['searchCompletedAt']) < datetime.fromisoformat(report['createdAt']), '배치 확정 순서 오류')
    models = {h: json.loads(raw) for h, raw in read_catalog(ROOT/'data/models').items()}
    expected = {h for h, m in models.items() if m['id'] in expected_ids}
    require(len(expected) == 4 and set(report['modelHashes']) == expected and len(report['modelHashes']) == 4, '공간 버전별 고정 강우 목록 오류')
    models = {h: models[h] for h in report['modelHashes']}
    require(all(m['cells'] == next(iter(models.values()))['cells'] for m in models.values()), '기준안 공간 버전 혼합')
    training = models[report['trainingModelHash']]
    require(training['id'] == training_id and report['engineRevision'] == swmm.REVISION, '탐색 모델·엔진 불일치')
    for model in models.values():
        for field in ['cells', 'unitCosts', 'budget', 'maxPlacements', 'hydrology', 'generatorSha256', 'engineRevision', 'geometrySourceHash']:
            require(model[field] == training[field], '물리 조건 호환 불가')
    recorded = {}
    for row in ledger:
        k = key(row['placements'])
        require(k not in recorded and row['cost'] == cost(training, row['placements']), '원장 중복·비용 오류')
        require(math.isfinite(row['accountedDischargeM3']) and row['accountedDischargeM3'] >= 0 and abs(row['runoffContinuityPercent']) <= 1, '후보 수치 품질 실패')
        recorded[k] = row['accountedDischargeM3']
    if rerun_candidates:
        with tempfile.TemporaryDirectory() as tmp:
            for row in ledger:
                actual = swmm.run(training, row['placements'], tmp, 'candidate')
                require(close(actual['accountedDischargeM3'], row['accountedDischargeM3']) and close(actual['runoffContinuityPercent'], row['runoffContinuityPercent']), '후보 원장 실제 계산 불일치')
    require(len(ledger) == report['uniqueCandidateEvaluations'] <= 2000, '후보 계산 횟수 오류')
    require([p['budget'] for p in report['plans']] == [30000000, 100000000, 300000000], '예산 목록 오류')
    used = set()
    def evaluate(placements):
        k = key(placements)
        used.add(k)
        return recorded[k]
    for plan in report['plans']:
        replay = search(training, plan['budget'], evaluate)
        replay['candidateEvaluations'] = replay.pop('evaluations')
        require(all(plan[k] == v for k, v in replay.items()), '탐색 원장 재생 불일치')
        require(plan['id'] == f"cpu-{plan['budget']}" and plan['cost'] <= plan['budget'], '배치 식별·예산 오류')
        require({e['modelHash'] for e in plan['evaluations']} == set(models) and len(plan['evaluations']) == len(models), '비교 강우 누락·중복')
        for e in plan['evaluations']:
            model = models[e['modelHash']]
            role = 'SEARCH_INPUT' if e['modelHash'] == report['trainingModelHash'] else 'POST_SELECTION_COMPARISON'
            require(e['role'] == role, '탐색/후속 비교 역할 오류')
            require(all(model['rainfall'][k] == v for k, v in e['rainfall'].items()), '강우 메타데이터 불일치')
            for group in ['baseline', 'strategy']:
                require(e[group]['routingContinuityPercent'] is None and e[group]['routingStatus'] == 'NOT_APPLICABLE_NO_CONVEYANCE_NETWORK', '관망 없는 계산의 유효성 오류')
                require(all(isinstance(v, (int, float)) and math.isfinite(v) for k, v in e[group].items() if k not in ('routingContinuityPercent', 'routingStatus')), '계산 지표 오류')
                require(abs(e[group]['runoffContinuityPercent']) <= 1, '계산 수지 오류')
            baseline = e['baseline']['accountedDischargeM3']
            score = (baseline-e['strategy']['accountedDischargeM3'])/baseline*100
            require(close(score, e['score']), '점수 체적 계약 불일치')
            if rerun:
                with tempfile.TemporaryDirectory() as tmp:
                    actual = swmm.experiment(model, plan['placements'], Path(tmp))
                for group in ['baseline', 'strategy']:
                    for k, v in e[group].items():
                        matches = close(actual[group][k], v) if isinstance(v, (int, float)) else actual[group][k] == v
                        require(matches, f'실제 엔진 재계산 불일치: {group}.{k}')
                require(close(actual['score'], e['score']), '실제 점수 재계산 불일치')
                for a, b in zip(actual['sensitivity'], e['sensitivity'], strict=True):
                    require(all(close(a[k], v) for k, v in b.items()), '민감도 재계산 불일치')
        require(plan['sampleScoreRange'] == {'min': min(e['score'] for e in plan['evaluations']), 'max': max(e['score'] for e in plan['evaluations'])}, '표본 범위 불일치')
    require(used == set(recorded) and sum(p['candidateEvaluations'] for p in report['plans']) == report['totalCandidateRequests'], '후보 원장 범위·요청 횟수 불일치')
    print(f"{training_id} CPU 기준안 검증 완료: 고유 후보 {len(ledger)}개, 예산 3개, 강우 {len(models)}개, 실제 재계산 {rerun}")


def verify(rerun=False, rerun_candidates=False):
    families = [
        ('cpu-reference.json', 'cpu-search-ledger.json', 'scripts/build_references.py',
         'seongsu-421-20240718', {'seongsu-exploratory-v1','seongsu-421-20240622','seongsu-421-20240702','seongsu-421-20240718'}),
        ('cpu-reference-ngii-v2.json', 'cpu-search-ledger-ngii-v2.json', 'scripts/build_topography_references.py',
         'seongsu-ngii-v2-421-20240718', {'seongsu-ngii-v2-108-20240718','seongsu-ngii-v2-421-20240622','seongsu-ngii-v2-421-20240702','seongsu-ngii-v2-421-20240718'}),
    ]
    catalog_path = ROOT/'data/derived/reference-catalog.json'
    require(catalog_path.read_bytes() == (ROOT/'backend/src/main/resources/models/reference-catalog.json').read_bytes(), '기준안 목록 사본 불일치')
    catalog = json.loads(catalog_path.read_text())
    require(catalog['schemaVersion'] == 1 and len(catalog['references']) == len(families), '기준안 목록 형식 오류')
    all_hashes = []
    for entry, config in zip(catalog['references'], families, strict=True):
        require(entry['reportFile'] == config[0] and entry['ledgerFile'] == config[1], '기준안 파일 연결 오류')
        report = json.loads((ROOT/'data/derived'/config[0]).read_text())
        require(entry['reportSha256'] == digest(ROOT/'data/derived'/config[0]) and entry['modelHashes'] == report['modelHashes'], '기준안 목록 해시 연결 오류')
        all_hashes.extend(entry['modelHashes'])
        verify_family(*config, rerun, rerun_candidates)
    require(len(all_hashes) == len(set(all_hashes)) and set(all_hashes) == set(read_catalog(ROOT/'data/models')), '모델 기준안 연결 누락·중복')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--rerun', action='store_true')
    parser.add_argument('--rerun-candidates', action='store_true')
    args = parser.parse_args()
    verify(args.rerun, args.rerun_candidates)
