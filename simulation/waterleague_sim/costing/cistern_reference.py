"""회원 관망 설계 용량과 공개 견적의 별도 비교 기록."""
from decimal import Decimal
from .cistern import CATALOG_PATH, CATALOG_SHA256, catalog, estimate
from ..engine.flood_errors import require
from ..engine.swmm import ROOT
from ..ingestion.published_network import digest
import json


def snapshot(placements):
    source = catalog()
    unit = Decimal(source['unitCapacityM3'])
    items = []
    for p in sorted(placements, key=lambda p: p['id']):
        if p['facilityType'] != 'RAINWATER_CISTERN':
            continue
        capacity = Decimal(str(p['areaM2'])) * Decimal(str(p['parameters']['storageDepthMm'])) / 1000
        number = capacity / unit
        units = int(number) if number == number.to_integral_value() and 1 <= number <= 256 else None
        quotes = []
        if units is not None:
            for row in source['quotes']:
                value = estimate(row['id'], units)
                initial, annual = value['initial'], value['annualOperation']
                quotes.append({'id': row['id'], 'quotedSubtotalKrw': initial['quotedSubtotalKrw'],
                    'materialsKrw': initial['materialsKrw'],
                    'components': {c['id']: c['amountKrw'] for c in initial['components']},
                    'unclassifiedDifferenceKrw': initial['unclassifiedDifferenceKrw'],
                    'annualComponentsKrw': {c['id']: c['annualAmountKrw'] for c in annual['components']},
                    'annualEstimateKrw': annual['estimatedKrw']})
        items.append({'placementId': p['id'], 'capacityM3': float(capacity),
            'equivalentUnits': units, 'status': 'CAPACITY_NOT_MATCHED' if units is None else 'CAPACITY_EQUIVALENT_ONLY',
            'quotes': quotes})
    require(bool(items), 'WATERSHED_CISTERN_COST_PLACEMENTS_REQUIRED')
    return {'schemaVersion': 1, 'catalogHash': CATALOG_SHA256,
        'method': 'CAPACITY_EQUIVALENT_QUOTES_NOT_ASSEMBLY_MATCH_V1', 'unitCapacityM3': float(unit),
        'items': items, 'source': source['source'], 'limitations': source['limitations'],
        'completeInstalledCostKrw': None, 'budgetChargedKrw': None}


def verify(design):
    if 'cisternCosting' not in design:
        return None
    require(design['cisternCosting'] == snapshot(design['placements']), 'WATERSHED_CISTERN_COST_CHANGED')
    return CATALOG_PATH.read_bytes()


def source_artifacts():
    manifest = (ROOT/'data/manifests/jkswe-cistern-costs-2018.json').read_bytes()
    source = catalog()['source']
    metadata = json.loads(manifest)
    raw = (ROOT/'data/private/facility-reference-20261018/jkswe-lid-costs-2018.html').read_bytes()
    require(metadata['source'] == source and metadata['raw']['sha256'] == digest(raw) == source['sha256']
        and metadata['extraction']['catalogSha256'] == CATALOG_SHA256, 'WATERSHED_CISTERN_QUOTE_SOURCE_CHANGED')
    return {'cistern-quote-source.html': raw, 'cistern-quote-source-manifest.json': manifest}
