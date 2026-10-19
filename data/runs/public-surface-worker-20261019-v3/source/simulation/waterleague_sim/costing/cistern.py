"""공개 2.35m³ 이용조 견적의 수량 내역과 별도 연간 유지비."""
from copy import deepcopy
from decimal import Decimal
import json

from waterleague_sim.engine.flood_errors import require
from waterleague_sim.engine.swmm import ROOT
from waterleague_sim.ingestion.published_network import digest

CATALOG_PATH = ROOT / 'backend/src/main/resources/facilities/cistern-costs-v1.json'
CATALOG_SHA256 = '63186839053e9a254bc42ba25765dfb78831d5621a3382e5abe0d110ddb7fe3b'


def catalog():
    raw = CATALOG_PATH.read_bytes()
    require(digest(raw) == CATALOG_SHA256, 'FACILITY_COST_CATALOG_CHANGED')
    return json.loads(raw)


def _amount(value):
    result = Decimal(value)
    require(result == result.to_integral_value(), 'FACILITY_COST_FRACTIONAL_WON')
    return int(result)


def estimate(quote_id, units):
    source = catalog()
    require(type(units) is int and 1 <= units <= 256, 'FACILITY_COST_QUANTITY_INVALID')
    require(type(quote_id) is str, 'FACILITY_COST_QUOTE_INVALID')
    quote = next((q for q in source['quotes'] if q['id'] == quote_id), None)
    require(quote is not None, 'FACILITY_COST_QUOTE_INVALID')
    components = []
    for key, value in quote['components'].items():
        components.append({'id': key, 'label': source['componentLabels'][key], 'quantity': units,
            'quantityUnit': 'QUOTED_BUNDLE', 'unitCostKrw': value,
            'amountKrw': None if value is None else units * value,
            'status': 'NOT_SEPARATELY_STATED' if value is None else 'STATED_IN_TABLE_9'})
    require(sum(c['unitCostKrw'] or 0 for c in components) == quote['materialsKrw'],
            'FACILITY_COST_SOURCE_TOTAL_MISMATCH')
    # 표의 총액·자재 소계 차액은 보존하되 노무비나 세금으로 임의 분류하지 않는다.
    remainder = quote['totalKrw'] - quote['materialsKrw']
    require(remainder >= 0, 'FACILITY_COST_SOURCE_TOTAL_MISMATCH')
    initial = units * quote['totalKrw']
    operation = [{'id': row['id'], 'label': row['label'], 'basisAmountKrw': initial,
                  'rate': row['rate'], 'annualAmountKrw': _amount(Decimal(initial) * Decimal(row['rate']))}
                 for row in source['annualOperation']['ratesOnInitialCost']]
    cleaning = source['annualOperation']['cleaning']
    operation.append({'id': 'CLEANING', 'label': '청소', 'quantity': units,
        'annualUnitCostKrw': _amount(Decimal(cleaning['costKrw']) / cleaning['households']),
        'annualAmountKrw': _amount(Decimal(cleaning['costKrw']) * units / cleaning['households'])})
    return {'schemaVersion': 1, 'catalogId': source['id'], 'catalogSha256': CATALOG_SHA256,
        'quoteId': quote_id, 'currency': source['currency'], 'units': units,
        'unitCapacityM3': source['unitCapacityM3'],
        'totalCapacityM3': str(Decimal(source['unitCapacityM3']) * units),
        'initial': {'quotedSubtotalKrw': initial, 'completeInstalledCostKrw': None,
                    'materialsKrw': units * quote['materialsKrw'], 'components': components,
                    'unclassifiedDifferenceKrw': units * remainder},
        'quoteRange': {'minimumKrw': units * min(q['totalKrw'] for q in source['quotes']),
                       'maximumKrw': units * max(q['totalKrw'] for q in source['quotes']),
                       'basis': 'THREE_PUBLISHED_QUOTES_NOT_CONFIDENCE_INTERVAL'},
        'annualOperation': {'estimatedKrw': sum(row['annualAmountKrw'] for row in operation),
                            'components': operation, 'basis': source['annualOperation']['basis'],
                            'reference': source['annualOperation']['reference']},
        'source': deepcopy(source['source']), 'scope': deepcopy(source['scope']),
        'limitations': list(source['limitations']),
        'eligibleForBudgetCharge': False, 'historicalPriceEligible': False,
        'currentPriceEligible': False}
