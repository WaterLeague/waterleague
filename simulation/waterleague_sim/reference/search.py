"""10m² 증분의 결정적 탐욕 탐색. 목적함수는 호출자가 제공한 한 모델만 사용."""
from decimal import Decimal
import math


def cost(model, placements):
    cells = {c['id']: c for c in model['cells']}
    seen = set()
    total = Decimal(0)
    if len(placements) > model['maxPlacements']:
        raise ValueError('시설 수 초과')
    for p in placements:
        cell = cells.get(p['cellId'])
        area = Decimal(str(p['areaM2']))
        if not cell or p['cellId'] in seen or p['facilityType'] not in cell['allowedTypes'] or not area.is_finite() or area <= 0 or area > Decimal(str(cell['maxAreaM2'])) or area.normalize().as_tuple().exponent < -2:
            raise ValueError('배치 조건 오류')
        seen.add(p['cellId'])
        total += area * Decimal(str(model['unitCosts'][p['facilityType']]))
    if total > Decimal(str(model['budget'])):
        raise ValueError('모델 예산 초과')
    return total


def key(placements):
    return tuple((p['cellId'], p['facilityType'], p['areaM2']) for p in sorted(placements, key=lambda p: p['cellId']))


def candidates(model, placements, budget, step=10):
    current = {p['cellId']: p for p in placements}
    for cell in sorted(model['cells'], key=lambda c: c['id']):
        old = current.get(cell['id'])
        types = [old['facilityType']] if old else sorted(cell['allowedTypes'])
        for facility in types:
            area = (old['areaM2'] if old else 0) + step
            if area > cell['maxAreaM2'] or not old and len(placements) >= model['maxPlacements']:
                continue
            trial = sorted([p for p in placements if p['cellId'] != cell['id']] + [{'cellId': cell['id'], 'facilityType': facility, 'areaM2': area}], key=lambda p: p['cellId'])
            if cost(model, trial) <= Decimal(str(budget)):
                yield trial


def search(model, budget, evaluate, *, max_evaluations=2000):
    if not 0 < budget <= model['budget'] or not 1 <= max_evaluations <= 2000:
        raise ValueError('탐색 한도 오류')
    placements = []
    baseline = evaluate(placements)
    if not math.isfinite(baseline) or baseline < 0:
        raise ValueError('비정상 기준 체적')
    current = baseline
    spent = Decimal(0)
    stages = []
    evaluated = 1
    # 보고서 0.001mm 반올림과 네 체적 항의 차분 오차보다 큰 개선만 채택한다.
    tolerance = sum(c['areaM2'] for c in model['cells']) * 0.004 / 1000
    while True:
        best = None
        for trial in candidates(model, placements, budget):
            if evaluated >= max_evaluations:
                return {'placements': placements, 'cost': int(spent), 'evaluations': evaluated, 'stages': stages, 'stopReason': 'EVALUATION_LIMIT', 'comparisonToleranceM3': tolerance}
            discharge = evaluate(trial)
            evaluated += 1
            if not math.isfinite(discharge) or discharge < 0:
                raise ValueError('비정상 후보 체적')
            trial_cost = cost(model, trial)
            gain = current - discharge
            if gain <= tolerance:
                continue
            order = (-gain/float(trial_cost-spent), trial_cost, key(trial))
            if best is None or order < best[0]:
                best = (order, trial, trial_cost, discharge, gain)
        if best is None:
            return {'placements': placements, 'cost': int(spent), 'evaluations': evaluated, 'stages': stages, 'stopReason': 'NO_POSITIVE_FEASIBLE_INCREMENT', 'comparisonToleranceM3': tolerance}
        _, placements, spent, current, gain = best
        stages.append({'placements': placements, 'cost': int(spent), 'accountedDischargeM3': current, 'incrementReductionM3': gain})
