"""설치 시점의 원가 원문을 입력·수량·출처와 대조해 계산 묶음에 보존."""
from decimal import Decimal
import hashlib
import json
from pathlib import Path


class CostEvidenceError(ValueError):
    def __init__(self):
        super().__init__('INSTALLATION_COST_EVIDENCE_INVALID')


def archive(request, model, placement, directory):
    raw, sha = request.get('costSnapshotRaw'), request.get('costSnapshotSha256')
    if raw is None and sha is None:
        return {'status': 'NOT_RECORDED', 'sha256': None, 'estimate': None}
    try:
        if (not isinstance(raw, str) or len(raw.encode()) > 65536
                or hashlib.sha256(raw.encode()).hexdigest() != sha):
            raise CostEvidenceError()
        value = json.loads(raw, parse_float=Decimal)
        link = model['sharedSiteSource']
        # 출처에 포함된 소수 규격도 원장과 같은 십진수로 비교한다.
        source = json.loads(json.dumps(model['costModel']['facilities'][placement['facilityType']],
                                       allow_nan=False), parse_float=Decimal)
        unit = Decimal(str(model['unitCosts'][placement['facilityType']]))
        area = Decimal(str(placement['areaM2']))
        amount = area * unit
        expected = {
            'version': 'PUBLIC_REFERENCE_QUANTITY_V2' if 'priceAdjustment' in source else 'PUBLIC_REFERENCE_QUANTITY_V1', 'currency': 'KRW',
            'districtId': link['districtId'], 'siteModelHash': link['siteCatalogHash'],
            'cellId': placement['cellId'], 'facilityType': placement['facilityType'],
            'quantityM2': area, 'unitCostKrw': unit, 'referenceSubtotalKrw': amount,
            'budgetChargeKrw': amount, 'completeInstalledCostKrw': None, 'priceBaseYear': None,
            'vat': 'UNCONFIRMED', 'priceAdjustment': source.get('priceAdjustment', {}).get('method', 'NONE'), 'currentPriceVerified': False,
            'historicalPriceEligible': False, 'costSourceSha256': model['costSourceSha256'],
            'source': source,
            'lines': [{'id': 'REFERENCE_INSTALLATION', 'label': source['scope'], 'quantity': area,
                       'quantityUnit': 'M2', 'unitCostKrw': unit, 'amountKrw': amount}],
            'unpricedItems': [{'label': label, 'amountKrw': None, 'status': 'UNPRICED'}
                             for label in source['excludes']],
        }
        if (value != expected or area <= 0 or unit <= 0 or source['unitCost'] != unit
                or (request.get('installationCostKrw') is not None
                    and Decimal(str(request['installationCostKrw'])) != amount)):
            raise CostEvidenceError()
    except (KeyError, TypeError, ValueError, ArithmeticError):
        raise CostEvidenceError() from None
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    (directory/'cost-snapshot.json').write_bytes(raw.encode())
    (directory/'cost_snapshot.py').write_bytes(Path(__file__).read_bytes())
    return {'status': 'RECORDED', 'sha256': sha, 'estimate': json.loads(raw)}
