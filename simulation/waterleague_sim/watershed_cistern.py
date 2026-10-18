"""회원 이용조 집수·배수 연결의 공개 원본 대조."""
import json
from .engine.cistern_network import compile_cistern
from .engine.flood_errors import require
from .ingestion.published_network import digest, records
from .watershed_storage import CATALOG, CATALOG_HASH


def compile(raw, design, base, placements, ids):
    data = CATALOG.read_bytes()
    require(digest(data) == CATALOG_HASH and isinstance(design, dict)
        and design.get('catalogHash') == CATALOG_HASH, 'WATERSHED_CISTERN_CATALOG_INVALID')
    catalog = json.loads(data)
    require(digest(base) == catalog['baseNetworkSha256'] == design.get('sourceNetworkSha256'),
        'WATERSHED_CISTERN_SOURCE_CHANGED')
    require(isinstance(design.get('id'), str) and design['id'].upper() not in {i.upper() for i in ids},
        'WATERSHED_CISTERN_ID_INVALID')
    require(not any(p['subcatchmentId'].upper() == str(design.get('subcatchmentId')).upper() for p in placements),
        'WATERSHED_CISTERN_SHARED_CATCHMENT_UNSUPPORTED')
    curve = design.get('depthAreaCurve')
    require(isinstance(curve, list) and len(curve) == 2
        and all(isinstance(p, dict) and p.get('areaM2') == design.get('footprintM2') for p in curve),
        'WATERSHED_CISTERN_PRISM_REQUIRED')
    # 기존 시설 추가 이후에도 집수구역 원 행과 연결 절점의 높이는 공개 원본과 같아야 한다.
    original, current = records(base)[1], records(raw)[1]
    host = next((r['tokens'] for r in original['SUBCATCHMENTS'] if r['tokens'][0] == design.get('subcatchmentId')), None)
    require(host is not None and any(r['tokens'] == host for r in current['SUBCATCHMENTS']),
        'WATERSHED_CISTERN_CATCHMENT_CHANGED')
    node = next((r['tokens'] for r in original['JUNCTIONS'] if r['tokens'][0] == host[2]), None)
    require(node is not None and any(r['tokens'] == node for r in current['JUNCTIONS']),
        'WATERSHED_CISTERN_RECEIVER_CHANGED')
    derived, metadata = compile_cistern(raw, {k: (digest(raw) if k == 'sourceNetworkSha256' else v)
        for k, v in design.items() if k != 'catalogHash'})
    metadata['memberCatalogHash'] = CATALOG_HASH
    metadata['baseNetworkSha256'] = digest(base)
    return derived, metadata
