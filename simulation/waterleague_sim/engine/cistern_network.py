"""강우 면적을 보존한 집수 분할과 수두 지배 이용조 배수 연결."""
from copy import deepcopy
import math
from pathlib import Path

from .connected_storage import append_section, capacity, identifier, indexed, number, SOURCE
from .flood_errors import require
from ..ingestion.published_network import digest, records

METHOD = 'COVERED_CISTERN_IMPERVIOUS_CAPTURE_DYNWAVE_V1'


def source_number(value):
    try:
        result = float(value)
    except (ValueError, TypeError):
        require(False, 'CISTERN_SOURCE_NUMBER_INVALID')
    require(math.isfinite(result), 'CISTERN_SOURCE_NUMBER_INVALID')
    return result


def compile_cistern(raw, design):
    text, sections = records(raw)
    require(isinstance(design, dict) and set(design) == {
        'schemaVersion', 'sourceNetworkSha256', 'id', 'subcatchmentId', 'captureAreaM2',
        'footprintM2', 'invertM', 'depthAreaCurve', 'initialDepthM', 'drain', 'overflow', 'evidence'}
        and type(design['schemaVersion']) is int and design['schemaVersion'] == 1
        and design['sourceNetworkSha256'] == digest(raw), 'CISTERN_SOURCE_BINDING_INVALID')
    require(isinstance(design['evidence'], str) and design['evidence'].strip(), 'CISTERN_EVIDENCE_REQUIRED')
    options = indexed(sections.get('OPTIONS', []))
    require(all(len(row) == 2 for row in options.values()), 'CISTERN_SOURCE_OPTION_INVALID')
    require(options.get('FLOW_UNITS', ['', ''])[1].upper() == 'CMS'
        and options.get('FLOW_ROUTING', ['', ''])[1].upper() == 'DYNWAVE'
        and options.get('LINK_OFFSETS', ['', 'DEPTH'])[1].upper() == 'DEPTH',
        'CISTERN_SI_DYNWAVE_DEPTH_REQUIRED')
    catchments = indexed(sections.get('SUBCATCHMENTS', []))
    host_id = identifier(design['subcatchmentId'], source=True).upper()
    require(host_id in catchments, 'CISTERN_CATCHMENT_MISSING')
    host = catchments[host_id]
    require(len(host) in (8, 9) and (len(host) == 8 or host[8] == '*')
        and source_number(host[4]) == 100, 'CISTERN_FULLY_IMPERVIOUS_HOST_REQUIRED')
    require(all(len(row) >= 3 for row in catchments.values()), 'CISTERN_SOURCE_CATCHMENT_INVALID')
    # 혼합 표면·추가 수문 상태를 단순 면적 분할로 재배분하지 않는다.
    for section in ('LID_USAGE', 'GROUNDWATER', 'GWF', 'COVERAGES', 'LOADINGS'):
        require(not any(row['tokens'][0].upper() == host_id for row in sections.get(section, [])),
                'CISTERN_HOST_ADDITIONAL_PROCESS_UNSUPPORTED')
    require(not sections.get('POLLUTANTS') and not sections.get('AQUIFERS'),
            'CISTERN_SOURCE_ADDITIONAL_PROCESS_UNSUPPORTED')
    require(not any(row[2].upper() == host_id for row in catchments.values()),
            'CISTERN_UPSTREAM_RUNON_UNSUPPORTED')
    subareas = indexed(sections.get('SUBAREAS', []))
    require(host_id in subareas and len(subareas[host_id]) >= 7
        and subareas[host_id][6].upper() == 'OUTLET', 'CISTERN_SUBAREA_ROUTING_UNSUPPORTED')
    internal = indexed(sections.get('JUNCTIONS', []) + sections.get('STORAGE', []))
    require(not any(name.startswith('WLCT_') for name in internal),
            'CISTERN_ALREADY_DERIVED_SOURCE_UNSUPPORTED')
    target = host[2].upper()
    require(target in internal, 'CISTERN_INTERNAL_OUTLET_REQUIRED')
    require(len(internal[target]) >= 3, 'CISTERN_SOURCE_NODE_INVALID')
    graph = {}
    for section in ('CONDUITS', 'PUMPS', 'ORIFICES', 'WEIRS', 'OUTLETS'):
        for row in sections.get(section, []):
            t = row['tokens']
            require(len(t) >= 3, 'CISTERN_SOURCE_LINK_INVALID')
            graph.setdefault(t[1].upper(), set()).add(t[2].upper())
    seen, todo = set(), [target]
    while todo:
        node = todo.pop()
        if node in seen: continue
        seen.add(node); todo.extend(graph.get(node, set()) - seen)
    require(seen.intersection(indexed(sections.get('OUTFALLS', []))), 'CISTERN_OUTFALL_CONNECTION_REQUIRED')
    area = number(source_number(host[3]), positive=True) * 10000
    width = number(source_number(host[5]), positive=True)
    capture = number(design['captureAreaM2'], positive=True)
    footprint = number(design['footprintM2'], positive=True)
    require(capture + footprint <= area, 'CISTERN_CAPTURE_FOOTPRINT_OVERLAP')
    volume = capacity(design['depthAreaCurve'])
    require(max(p['areaM2'] for p in design['depthAreaCurve']) <= footprint,
            'CISTERN_STORAGE_EXCEEDS_FOOTPRINT')
    depth = design['depthAreaCurve'][-1]['depthM']
    invert = number(design['invertM'], -1000, 10000)
    initial = number(design['initialDepthM'], high=depth)
    name = 'WLCT_' + identifier(design['id'])
    child, curve = name + '_C', name + '_A'
    names = {name.upper(), child.upper(), curve.upper(), (name+'_D').upper(), (name+'_O').upper()}
    existing = {t.upper() for rows in sections.values() for r in rows for t in r['tokens']}
    require(not names.intersection(existing), 'CISTERN_ID_COLLISION')
    added = {'SUBCATCHMENTS': [], 'SUBAREAS': [], 'INFILTRATION': [], 'STORAGE': [],
             'CURVES': [], 'ORIFICES': [], 'XSECTIONS': []}
    remaining = host[:]
    remaining[3], remaining[5] = format((area-capture)/10000, '.15g'), format(width*(area-capture)/area, '.15g')
    diverted = host[:]
    diverted[0:3] = [child, host[1], name]
    diverted[3], diverted[5] = format(capture/10000, '.15g'), format(width*capture/area, '.15g')
    added['SUBCATCHMENTS'].append(' '.join(diverted))
    added['SUBAREAS'].append(' '.join([child, *subareas[host_id][1:]]))
    infiltration = indexed(sections.get('INFILTRATION', []))
    if host_id in infiltration:
        added['INFILTRATION'].append(' '.join([child, *infiltration[host_id][1:]]))
    rewritten = [host, subareas[host_id], infiltration.get(host_id, [])]
    require(all(not any(c.isspace() or c in '\"\'' for c in token)
                for row in rewritten for token in row), 'CISTERN_SOURCE_QUOTED_TOKEN_UNSUPPORTED')
    added['STORAGE'].append(f'{name} {invert:.15g} {depth:.15g} {initial:.15g} TABULAR {curve} 0 0')
    for i, p in enumerate(design['depthAreaCurve']):
        added['CURVES'].append(f'{curve} {"STORAGE " if i == 0 else ""}{p["depthM"]:.15g} {p["areaM2"]:.15g}')
    ports = {}
    for kind, suffix in (('drain', 'D'), ('overflow', 'O')):
        p = design[kind]
        require(isinstance(p, dict) and set(p) == {'crestM', 'diameterM', 'dischargeCoefficient', 'flapGate'},
                'CISTERN_PORT_INVALID')
        crest = number(p['crestM'], -1000, 10000)
        diameter = number(p['diameterM'], high=100, positive=True)
        coefficient = number(p['dischargeCoefficient'], high=1, positive=True)
        require(type(p['flapGate']) is bool, 'CISTERN_FLAP_INVALID')
        target_invert, target_depth = source_number(internal[target][1]), source_number(internal[target][2])
        require(all(math.isfinite(v) for v in (target_invert, target_depth)) and target_depth > 0
            and max(invert, target_invert) <= crest
            and crest+diameter <= min(invert+depth, target_invert+target_depth), 'CISTERN_PORT_ELEVATION_INVALID')
        link = name+'_'+suffix
        added['ORIFICES'].append(f'{link} {name} {host[2]} SIDE {crest-invert:.15g} '
            f'{coefficient:.15g} {"YES" if p["flapGate"] else "NO"} 0')
        added['XSECTIONS'].append(f'{link} CIRCULAR {diameter:.15g} 0 0 0')
        ports[kind] = {'linkId': link, 'nodeId': host[2], **deepcopy(p)}
    require(design['overflow']['crestM'] > design['drain']['crestM'], 'CISTERN_OVERFLOW_LEVEL_INVALID')
    ending = '\r\n' if '\r\n' in text else '\n'
    lines = text.splitlines(keepends=True)
    row = next(r for r in sections['SUBCATCHMENTS'] if r['tokens'][0].upper() == host_id)
    # 균질 불투수면의 폭/면적 비를 보존하여 분할 자체가 새로운 유출 지연을 만들지 않게 한다.
    comment = lines[row['line']-1].split(';', 1)
    lines[row['line']-1] = ' '.join(remaining) + (' ;'+comment[1].rstrip('\r\n') if len(comment)>1 else '') + ending
    for section, rows in added.items():
        if rows: append_section(lines, section, rows, ending)
    result = ''.join(lines).encode()
    require(len(result) <= 2_000_000, 'CISTERN_INPUT_TOO_LARGE')
    return result, {'schemaVersion': 1, 'method': METHOD, 'source': SOURCE,
        'sourceNetworkSha256': digest(raw), 'derivedNetworkSha256': digest(result),
        'compilerSha256': digest(Path(__file__).read_bytes()), 'design': deepcopy(design),
        'catchmentPartition': {'hostId': host[0], 'captureId': child, 'originalAreaM2': area,
            'bypassAreaM2': area-capture, 'captureAreaM2': capture, 'coverAreaM2': footprint,
            'originalWidthM': width, 'bypassWidthM': float(remaining[5]), 'captureWidthM': float(diverted[5]),
            'coverRainfallRoute': 'BYPASS_CATCHMENT_TO_ORIGINAL_OUTLET', 'rainfallCount': 1,
            'captureBasis': 'EXPLICIT_DESIGN_UNIFORM_IMPERVIOUS_PARTITION_NOT_MEASURED_ROOF'},
        'facilities': [{'id': design['id'], 'nodeId': name, 'facilityType': 'RAINWATER_CISTERN',
            'capacityM3': volume, 'ports': ports, 'directRainfallM3': 0, 'evaporationFactor': 0,
            'seepageMmH': 0, 'surfaceOwnership': 'COVER_RETAINS_ORIGINAL_IMPERVIOUS_BYPASS',
            'geometryVerifiedOnSite': False}],
        'rankingEligible': False, 'historicalReconstructionEligible': False,
        'limitations': ['전면 불투수 집수의 명시적 균질 분할; 실제 지붕·홈통 연결 관측 아님',
            '기존 강우 면적·조도·요지저류·폭/면적 보존, 덮개 강우는 원 출구로 우회',
            '집수 유출은 이용조 측방 유입으로 연결; 홈통 용량·막힘·역류의 지붕 재유입 미모형화',
            '배수·비상구의 관망 수두 및 역류 반영; 접속관 마찰은 별도 설계 필요',
            '포화 토양·수질·수요·펌프 없는 재이용 저감점수 부여 금지',
            '비상구 용량 초과에 따른 이용조 절점 월류는 실패로 보존']}
