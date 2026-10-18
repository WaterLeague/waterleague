"""회원 저류조 설계와 공개 관망 연결 원본의 대조."""
import json
from .engine.swmm import ROOT
from .engine.connected_storage import compile_storage
from .engine.flood_errors import require
from .ingestion.published_network import digest

CATALOG = ROOT/'backend/src/main/resources/watersheds/seocho-storage-connections-v1.json'
CATALOG_HASH = 'f2df891f3914de02c37ff7ae09f6d5a849ef6f69dae85e25e562e5a44cffc105'


def compile(raw, design, lid_ids):
    data = CATALOG.read_bytes()
    require(digest(data) == CATALOG_HASH and isinstance(design, dict)
            and set(design) == {'catalogHash', 'schemaVersion', 'sourceNetworkSha256', 'placements'}
            and design['catalogHash'] == CATALOG_HASH, 'WATERSHED_STORAGE_CATALOG_INVALID')
    catalog = json.loads(data)
    require(digest(raw) == catalog['baseNetworkSha256'] == design['sourceNetworkSha256'],
            'WATERSHED_STORAGE_SOURCE_CHANGED')
    pairs = {(c['inlet']['id'], c['receiver']['id']) for c in catalog['connections']}
    require(isinstance(design['placements'], list) and 0 < len(design['placements']) <= 20,
            'WATERSHED_STORAGE_PLACEMENTS_INVALID')
    names = {name.upper() for name in lid_ids}
    for p in design['placements']:
        require(isinstance(p, dict) and isinstance(p.get('id'), str) and p['id'].upper() not in names,
                'WATERSHED_STORAGE_ID_INVALID')
        names.add(p['id'].upper())
        require(all(isinstance(p.get(key), dict) for key in ('inlet', 'drain', 'overflow'))
                and (p['inlet'].get('nodeId'), p['drain'].get('nodeId')) in pairs
                and p['drain'].get('nodeId') == p['overflow'].get('nodeId'),
                'WATERSHED_STORAGE_CONNECTION_INVALID')
    return compile_storage(raw, {key: value for key, value in design.items() if key != 'catalogHash'})
