"""계산에 사용한 개별 이용조 용량과 공개 견적을 결합한 불변 입력."""
from collections import Counter
from copy import deepcopy
from decimal import Decimal
from pathlib import Path

from waterleague_sim.costing.cistern import catalog, estimate, CATALOG_SHA256
from waterleague_sim.engine.connected_facilities import compile_design
from waterleague_sim.engine.flood_errors import require
from waterleague_sim.ingestion.published_network import digest


def compile_priced_design(raw, design, costing):
    derived, metadata = compile_design(raw, design)
    require(isinstance(costing, dict) and set(costing) == {'schemaVersion', 'catalogSha256', 'items'}
            and type(costing['schemaVersion']) is int and costing['schemaVersion'] == 1
            and costing['catalogSha256'] == CATALOG_SHA256, 'FACILITY_COST_REQUEST_INVALID')
    items = costing['items']
    require(isinstance(items, list) and len(items) <= 256, 'FACILITY_COST_ITEMS_INVALID')
    source = catalog()
    placements = {p['id']: p for p in metadata['design']['placements']}
    assignments, seen, quantities = [], set(), Counter()
    for item in items:
        require(isinstance(item, dict) and set(item) == {'placementId', 'quoteId'}
                and type(item['placementId']) is str and type(item['quoteId']) is str,
                'FACILITY_COST_ITEM_INVALID')
        key, quote = item['placementId'], item['quoteId']
        require(key in placements and key not in seen, 'FACILITY_COST_PLACEMENT_INVALID')
        seen.add(key)
        placement = placements[key]
        require(placement['facilityType'] == source['facilityType'], 'FACILITY_COST_TYPE_MISMATCH')
        capacity = Decimal(str(placement['areaM2'])) * Decimal(str(placement['parameters']['storageDepthMm'])) / 1000
        # 큰 단일 물통을 여러 작은 설비 가격으로 나누면 배수·표면 형상이 달라지므로 거부한다.
        require(capacity == Decimal(source['unitCapacityM3']), 'FACILITY_COST_CAPACITY_MISMATCH')
        estimate(quote, 1)
        quantities[quote] += 1
        assignments.append({'placementId': key, 'quoteId': quote, 'quantity': 1,
            'computedCapacityM3': str(capacity), 'match': 'CAPACITY_ONLY_NOT_COMPONENT_SPECIFICATION',
            'physicalPlacementSha256': digest(_json(placement))})
    estimates = [estimate(quote, count) for quote, count in sorted(quantities.items())]
    unpriced = sorted(set(placements) - seen)
    result = {'schemaVersion': 1, 'catalogSha256': CATALOG_SHA256,
        'compilerSha256': digest(Path(__file__).read_bytes()),
        'calculatorSha256': digest((Path(__file__).parents[1] / 'costing/cistern.py').read_bytes()),
        'request': deepcopy(costing), 'assignments': sorted(assignments, key=lambda item: item['placementId']),
        'estimates': estimates, 'unpricedPlacementIds': unpriced,
        'pricedPlacementCount': len(seen), 'totalPlacementCount': len(placements),
        'knownQuotedSubtotalKrw': sum(row['initial']['quotedSubtotalKrw'] for row in estimates),
        'knownAnnualOperationEstimateKrw': sum(row['annualOperation']['estimatedKrw'] for row in estimates),
        'completeInstalledCostKrw': None, 'currency': 'KRW', 'eligibleForBudgetCharge': False,
        'historicalPriceEligible': False, 'currentPriceEligible': False}
    return derived, {**metadata, 'costing': result, 'costingSha256': digest(_json(result))}


def _json(value):
    import json
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
