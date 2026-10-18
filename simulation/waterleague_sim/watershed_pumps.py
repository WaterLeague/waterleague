"""회원 펌프 설계의 고정 공개 관망·곡선과 전체 입력 결속."""
from .engine.connected_pumps import compile_pumps, CATALOG_HASH
from .engine.flood_errors import require
from .ingestion.published_network import digest


def compile(raw, design, source_raw, used_ids):
    require(isinstance(design, dict) and set(design) == {'schemaVersion', 'catalogHash', 'sourceNetworkSha256', 'placements'}
        and design['catalogHash'] == CATALOG_HASH and design['sourceNetworkSha256'] == digest(source_raw),
        'WATERSHED_PUMP_SOURCE_INVALID')
    require(isinstance(design['placements'], list), 'WATERSHED_PUMP_PLACEMENTS_INVALID')
    names = {v.upper() for v in used_ids}
    for p in design['placements']:
        require(isinstance(p, dict) and isinstance(p.get('id'), str) and p['id'].upper() not in names,
                'WATERSHED_PUMP_DUPLICATE_ID')
        names.add(p['id'].upper())
    derived, metadata = compile_pumps(raw, {'schemaVersion': design['schemaVersion'],
        'sourceNetworkSha256': digest(raw), 'curveCatalogHash': design['catalogHash'], 'placements': design['placements']})
    metadata['baseNetworkSha256'] = digest(source_raw)
    return derived, metadata
