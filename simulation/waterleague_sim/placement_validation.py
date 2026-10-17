"""계산 입력의 시설·면적·원화 예산 검증."""
from decimal import Decimal


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

