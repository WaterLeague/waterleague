"""공개 사업계획 참고 금액의 서버 스냅샷을 물리 설계 수량과 대조."""
import json
from decimal import Decimal, ROUND_HALF_UP
from ..engine.flood_errors import require
from ..engine.swmm import ROOT
from ..ingestion.published_network import digest

CATALOG = ROOT / 'backend/src/main/resources/watersheds/connected-costs-v1.json'
CATALOG_HASH = '9a182d390c74c8adad4f14eb6d575e1a556057fb69b87e5b802ca131dcfc5739'


def snapshot(placements, catalog):
    items, unpriced = [], []
    subtotal = 0
    for p in sorted(placements, key=lambda p: p['id']):
        quote = catalog['entries'][p['facilityType']]
        amount = None
        if quote['status'] == 'AREA_REFERENCE_ONLY':
            amount = int((Decimal(str(p['areaM2'])) * Decimal(quote['unitPriceKrw']))
                         .quantize(Decimal('1'), rounding=ROUND_HALF_UP))
            subtotal += amount
        else:
            unpriced.append(p['id'])
        items.append({'placementId': p['id'], 'facilityType': p['facilityType'],
                      'areaM2': p['areaM2'], 'status': quote['status'],
                      'referenceAmountKrw': amount, 'notes': quote['notes']})
    return {'schemaVersion': 1, 'catalogHash': CATALOG_HASH,
            'classification': catalog['classification'], 'source': catalog['source'],
            'limitations': catalog['limitations'], 'items': items,
            'knownReferenceSubtotalKrw': subtotal if len(unpriced) < len(items) else None,
            'unpricedPlacementIds': unpriced, 'completeInstalledCostKrw': None,
            'budgetChargedKrw': None}


def verify(design):
    require(set(design) in ({'schemaVersion', 'basis', 'placements'},
                           {'schemaVersion', 'basis', 'placements', 'costing'}),
            'WATERSHED_DESIGN_INVALID')
    if 'costing' not in design:
        return None
    raw = CATALOG.read_bytes()
    require(digest(raw) == CATALOG_HASH, 'WATERSHED_COST_CATALOG_CHANGED')
    catalog = json.loads(raw)
    expected = snapshot(design['placements'], catalog)
    require(design['costing'] == expected, 'WATERSHED_COST_SNAPSHOT_MISMATCH')
    return raw
