"""회원 이용조 집수·배수 연결의 공개 원본 대조."""
import json
import re
from decimal import Decimal
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
    shared = [p for p in placements
              if p['subcatchmentId'].upper() == str(design.get('subcatchmentId')).upper()]
    require((design.get('schemaVersion') == 3) == bool(shared),
            'WATERSHED_CISTERN_SHARED_CATCHMENT_VERSION_REQUIRED')
    curve = design.get('depthAreaCurve')
    require(isinstance(curve, list) and len(curve) == 2
        and all(isinstance(p, dict) and p.get('areaM2') == design.get('footprintM2') for p in curve),
        'WATERSHED_CISTERN_PRISM_REQUIRED')
    # 기존 시설 추가 이후에도 집수구역 원 행과 연결 절점의 높이는 공개 원본과 같아야 한다.
    original, current = records(base)[1], records(raw)[1]
    host = next((r['tokens'] for r in original['SUBCATCHMENTS'] if r['tokens'][0] == design.get('subcatchmentId')), None)
    require(host is not None and any(r['tokens'] == host for r in current['SUBCATCHMENTS']),
        'WATERSHED_CISTERN_CATCHMENT_CHANGED')
    if shared:
        available = Decimal(host[3]) * 10000 * Decimal(host[4]) / 100
        used = Decimal(str(design['captureAreaM2'])) + Decimal(str(design['footprintM2']))
        lid_area = Decimal(0)
        for p in shared:
            require(p['facilityType'] != 'RAINWATER_CISTERN', 'WATERSHED_CISTERN_SHARED_COVERED_LID_UNSUPPORTED')
            require(p['replacedImperviousM2'] == p['areaM2'], 'WATERSHED_CISTERN_SHARED_IMPERVIOUS_REQUIRED')
            used += Decimal(str(p['areaM2'])) + Decimal(str(p['treatedImperviousM2']))
            lid_area += Decimal(str(p['areaM2']))
        require(used <= available, 'WATERSHED_CISTERN_SHARED_CAPTURE_AREA_EXCEEDED')
        free = available - Decimal(str(design['captureAreaM2'])) - Decimal(str(design['footprintM2']))
        require(lid_area <= free * Decimal('0.999'), 'WATERSHED_CISTERN_SHARED_FULL_LID_UNSUPPORTED')
    node = next((r['tokens'] for r in original['JUNCTIONS'] if r['tokens'][0] == host[2]), None)
    require(node is not None and any(r['tokens'] == node for r in current['JUNCTIONS']),
        'WATERSHED_CISTERN_RECEIVER_CHANGED')
    derived, metadata = compile_cistern(raw, {k: (digest(raw) if k == 'sourceNetworkSha256' else v)
        for k, v in design.items() if k != 'catalogHash'})
    metadata['memberCatalogHash'] = CATALOG_HASH
    metadata['baseNetworkSha256'] = digest(base)
    return derived, metadata


def prepare_lids(raw, design, metadata):
    from copy import deepcopy
    value = deepcopy(design)
    assignments = []
    if metadata is not None and metadata['schemaVersion'] == 3:
        require(digest(raw) == metadata['derivedNetworkSha256'], 'WATERSHED_CISTERN_SHARED_SOURCE_CHANGED')
        partition = metadata['catchmentPartition']
        for item in value['placements']:
            if item['subcatchmentId'].upper() == partition['hostId'].upper():
                require(item['facilityType'] != 'RAINWATER_CISTERN', 'WATERSHED_CISTERN_SHARED_COVERED_LID_UNSUPPORTED')
                original = item['subcatchmentId']
                item['subcatchmentId'] = partition['imperviousBypassId']
                assignments.append({'id': item['id'], 'sourceCatchmentId': original,
                                    'executionCatchmentId': item['subcatchmentId'],
                                    'policy': 'EXCLUDE_CISTERN_CAPTURE_AND_COVER'})
    if not assignments:
        return raw, value, assignments, None
    partition = metadata['catchmentPartition']
    host = partition['imperviousBypassId']
    rows = records(raw)[1]['SUBCATCHMENTS']
    source = next(r for r in rows if r['tokens'][0] == host)
    total = float(source['tokens'][3]) * 10000
    area = sum(p['areaM2'] for p in value['placements'] if p['subcatchmentId'] == host)
    require(0 < area <= .999 * total, 'WATERSHED_CISTERN_SHARED_FULL_LID_UNSUPPORTED')
    width = float(source['tokens'][5])
    adjusted = width * (total-area) / total
    lines = raw.decode('utf-8-sig').splitlines(keepends=True)
    line = lines[source['line']-1]
    match = re.match(r'(\s*(?:\S+\s+){5})(\S+)', line)
    require(match is not None, 'WATERSHED_CISTERN_SHARED_SOURCE_FORMAT_INVALID')
    # EPA의 분모는 LID 면적을 뺀 유효 면적이다. 잔여 표면의 원 유출 계수를 보존한다.
    lines[source['line']-1] = line[:match.start(2)] + format(adjusted, '.15g') + line[match.end(2):]
    result = ''.join(lines).encode()
    return result, value, assignments, {'sourceNetworkSha256': digest(raw), 'derivedNetworkSha256': digest(result),
        'executionCatchmentId': host, 'totalAreaM2': total, 'facilityAreaM2': area,
        'remainingNonLidAreaM2': total-area, 'originalWidthM': width,
        'remainingNonLidWidthM': adjusted, 'policy': 'PRESERVE_ORIGINAL_IMPERVIOUS_WIDTH_PER_NON_LID_AREA'}
