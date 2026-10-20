"""유한 지하 저류조와 수두 지배 유입·배수구의 관망 파생 입력."""
from collections import defaultdict, deque
from copy import deepcopy
import math
from pathlib import Path
import re

from waterleague_sim.engine.flood_errors import require
from waterleague_sim.ingestion.published_network import records, digest

METHOD = 'CONNECTED_COVERED_SEALED_STORAGE_V1'
SOURCE = {'title': 'EPA SWMM 5.2 User Manual',
    'url': 'https://nepis.epa.gov/Exe/ZyPURL.cgi?Dockey=P10145M6.TXT',
    'sections': ['3.2.6 Storage Units', 'B.6 Storage Unit Properties', 'C.20 Storage Shape Editor',
                 '[STORAGE]', '[ORIFICES]', '[XSECTIONS]'],
    'engineRevision': '7952ca837988b1c32f791812eccc9fd64547e093'}
CMS_STORAGE_VOLUME_SCALE = 0.028316846592 / 0.02832


def volume_properties(declared):
    # EPA 저장 곡선의 m³→ft³ 변환과 내부 ft³의 정확한 SI 환산을 구분한다.
    return {'nativeCapacityM3': declared * CMS_STORAGE_VOLUME_SCALE,
            'volumeBasis': 'EPA_CMS_STORAGE_VOLUME_TO_EXACT_SI_V1'}


def number(v, low=0., high=1e9, *, positive=False):
    require(type(v) in (int, float) and low <= v <= high and math.isfinite(v)
            and (not positive or v > 0), 'STORAGE_DESIGN_NUMBER_INVALID')
    return float(v)


def identifier(v, *, source=False):
    pattern = r'[A-Za-z0-9_][A-Za-z0-9_.-]{0,126}' if source else r'[A-Za-z][A-Za-z0-9_-]{0,23}'
    require(isinstance(v, str) and re.fullmatch(pattern, v),
            'STORAGE_DESIGN_IDENTIFIER_INVALID')
    return v


def indexed(rows):
    result = {}
    for row in rows:
        name = row['tokens'][0].upper()
        require(name not in result, 'STORAGE_DESIGN_SOURCE_DUPLICATE')
        result[name] = row['tokens']
    return result


def append_section(lines, section, rows, ending):
    markers = [i for i, line in enumerate(lines)
               if re.fullmatch(r'\s*\[' + section + r'\]\s*(?:;.*)?', line.rstrip('\r\n'), re.I)]
    require(len(markers) <= 1, 'STORAGE_DESIGN_SOURCE_DUPLICATE')
    if markers:
        lines[markers[0]+1:markers[0]+1] = [row+ending for row in rows]
    else:
        if lines and not lines[-1].endswith(('\r', '\n')):
            lines[-1] += ending
        lines.extend([ending, '['+section+']'+ending, *[row+ending for row in rows]])


def capacity(curve):
    require(isinstance(curve, list) and 2 <= len(curve) <= 512, 'STORAGE_DESIGN_CURVE_INVALID')
    points = []
    for row in curve:
        require(isinstance(row, dict) and set(row) == {'depthM', 'areaM2'}, 'STORAGE_DESIGN_CURVE_INVALID')
        depth, area = number(row['depthM'], high=100), number(row['areaM2'], positive=True)
        require(not points or depth > points[-1][0], 'STORAGE_DESIGN_CURVE_DEPTH_INVALID')
        points.append((depth, area))
    require(points[0][0] == 0 and points[-1][0] > 0, 'STORAGE_DESIGN_CURVE_COVERAGE_INVALID')
    return math.fsum((b[0]-a[0])*(a[1]+b[1])/2 for a, b in zip(points, points[1:]))


def compile_storage(raw, design):
    text, sections = records(raw)
    require(isinstance(design, dict) and set(design) == {'schemaVersion', 'sourceNetworkSha256', 'placements'}
            and type(design['schemaVersion']) is int and design['schemaVersion'] == 1
            and design['sourceNetworkSha256'] == digest(raw), 'STORAGE_DESIGN_SOURCE_BINDING_INVALID')
    placements = design['placements']
    require(isinstance(placements, list) and 0 < len(placements) <= 128, 'STORAGE_DESIGN_PLACEMENTS_INVALID')
    options = indexed(sections.get('OPTIONS', []))
    require(all(len(tokens) == 2 for tokens in options.values()), 'STORAGE_DESIGN_SOURCE_OPTION_INVALID')
    require(options.get('FLOW_UNITS', ['', ''])[1].upper() == 'CMS'
            and options.get('FLOW_ROUTING', ['', ''])[1].upper() == 'DYNWAVE'
            and options.get('LINK_OFFSETS', ['', 'DEPTH'])[1].upper() == 'DEPTH',
            'STORAGE_DESIGN_SI_DYNWAVE_DEPTH_REQUIRED')
    nodes = indexed([row for name in ('JUNCTIONS', 'STORAGE', 'OUTFALLS', 'DIVIDERS')
                     for row in sections.get(name, [])])
    outfalls = indexed(sections.get('OUTFALLS', []))
    internal = indexed(sections.get('JUNCTIONS', []) + sections.get('STORAGE', []))
    links = indexed([row for name in ('CONDUITS', 'PUMPS', 'ORIFICES', 'WEIRS', 'OUTLETS')
                     for row in sections.get(name, [])])
    curves = {row['tokens'][0].upper() for row in sections.get('CURVES', [])}
    source_tokens = {token.upper() for rows in sections.values() for row in rows for token in row['tokens']}
    graph = defaultdict(set)
    for tokens in links.values():
        require(len(tokens) >= 3 and all(token.upper() in nodes for token in tokens[1:3]),
                'STORAGE_DESIGN_SOURCE_LINK_INVALID')
        graph[tokens[1].upper()].add(tokens[2].upper())
    def downstream(source):
        seen, queue = {source}, deque([source])
        while queue:
            for target in graph[queue.popleft()]-seen:
                seen.add(target)
                queue.append(target)
        return seen
    added = {'STORAGE': [], 'CURVES': [], 'ORIFICES': [], 'XSECTIONS': []}
    details, names = [], set()
    require(all(isinstance(p, dict) and isinstance(p.get('id'), str) for p in placements),
            'STORAGE_DESIGN_PLACEMENT_INVALID')
    for p in sorted(placements, key=lambda row: row['id']):
        require(isinstance(p, dict) and set(p) == {'id', 'facilityType', 'basis', 'evidence', 'invertM',
            'depthAreaCurve', 'initialDepthM', 'surchargeDepthM', 'cover', 'lining', 'inlet', 'drain', 'overflow'},
            'STORAGE_DESIGN_PLACEMENT_INVALID')
        require(p['facilityType'] == 'UNDERGROUND_STORAGE' and p['basis'] == 'EXPLICIT_DESIGN_NOT_SITE_MEASURED'
                and isinstance(p['evidence'], str) and p['evidence'].strip()
                and p['cover'] == 'COVERED' and p['lining'] == 'SEALED', 'STORAGE_DESIGN_SCOPE_INVALID')
        name = 'WLST_'+identifier(p['id'])
        curve_name = name+'_A'
        generated = {name.upper()} | {(name+'_'+suffix).upper() for suffix in ('A', 'I', 'D', 'O')}
        require(not generated.intersection(source_tokens), 'STORAGE_DESIGN_ID_COLLISION')
        require(name.upper() not in nodes and name.upper() not in names
                and curve_name.upper() not in curves, 'STORAGE_DESIGN_ID_COLLISION')
        names.add(name.upper())
        invert = number(p['invertM'], -1000, 10000)
        volume = capacity(p['depthAreaCurve'])
        depth = p['depthAreaCurve'][-1]['depthM']
        initial = number(p['initialDepthM'], high=depth)
        surcharge = number(p['surchargeDepthM'], high=100)
        ports = {}
        for kind in ('inlet', 'drain', 'overflow'):
            port = p[kind]
            require(isinstance(port, dict) and set(port) == {'nodeId', 'crestM', 'diameterM',
                'dischargeCoefficient', 'flapGate', 'evidence'}, 'STORAGE_DESIGN_PORT_INVALID')
            target = identifier(port['nodeId'], source=True).upper()
            require(target in internal, 'STORAGE_DESIGN_INTERNAL_NODE_REQUIRED')
            require(type(port['flapGate']) is bool and isinstance(port['evidence'], str)
                    and port['evidence'].strip(), 'STORAGE_DESIGN_PORT_EVIDENCE_REQUIRED')
            crest = number(port['crestM'], -1000, 10000)
            diameter = number(port['diameterM'], high=100, positive=True)
            coefficient = number(port['dischargeCoefficient'], high=1, positive=True)
            try:
                node_invert = float(nodes[target][1])
                node_depth = float(nodes[target][2])
            except (ValueError, IndexError):
                require(False, 'STORAGE_DESIGN_SOURCE_NODE_INVALID')
            require(math.isfinite(node_invert) and math.isfinite(node_depth) and node_depth > 0
                    and max(invert, node_invert) <= crest
                    and crest+diameter <= min(invert+depth, node_invert+node_depth),
                    'STORAGE_DESIGN_PORT_ELEVATION_INVALID')
            link_name = name+'_'+{'inlet': 'I', 'drain': 'D', 'overflow': 'O'}[kind]
            require(link_name.upper() not in links, 'STORAGE_DESIGN_ID_COLLISION')
            source, destination, offset = (nodes[target][0], name, crest-node_invert) if kind == 'inlet' else (
                name, nodes[target][0], crest-invert)
            added['ORIFICES'].append(f'{link_name} {source} {destination} SIDE {offset:.15g} '
                                     f'{coefficient:.15g} {"YES" if port["flapGate"] else "NO"} 0')
            added['XSECTIONS'].append(f'{link_name} CIRCULAR {diameter:.15g} 0 0 0')
            ports[kind] = {'nodeId': nodes[target][0], 'linkId': link_name, 'crestM': crest,
                           'diameterM': diameter, 'dischargeCoefficient': coefficient,
                           'flapGate': port['flapGate']}
        source = p['inlet']['nodeId'].upper()
        reachable = downstream(source)
        require(reachable & set(outfalls) and all(p[k]['nodeId'].upper() in reachable-{source}
                and downstream(p[k]['nodeId'].upper()) & set(outfalls)
                for k in ('drain', 'overflow')), 'STORAGE_DESIGN_DOWNSTREAM_CONNECTION_REQUIRED')
        require(p['overflow']['crestM'] > p['drain']['crestM'], 'STORAGE_DESIGN_OVERFLOW_LEVEL_INVALID')
        added['STORAGE'].append(f'{name} {invert:.15g} {depth:.15g} {initial:.15g} TABULAR {curve_name} '
                                f'{surcharge:.15g} 0')
        for i, row in enumerate(p['depthAreaCurve']):
            added['CURVES'].append(f'{curve_name} {"STORAGE " if i == 0 else ""}'
                                   f'{row["depthM"]:.15g} {row["areaM2"]:.15g}')
        details.append({'id': p['id'], 'nodeId': name, 'facilityType': p['facilityType'],
            'capacityM3': volume, **volume_properties(volume), 'capacityMethod': 'EPA_TABULAR_END_AREA_INTEGRAL',
            'ports': ports, 'directRainfallM3': 0, 'evaporationFactor': 0, 'seepageMmH': 0,
            'surfaceOwnership': 'UNCHANGED_ABOVE_GROUND_CATCHMENTS', 'geometryVerifiedOnSite': False})
    ending = '\r\n' if '\r\n' in text else '\n'
    lines = text.splitlines(keepends=True)
    for section, rows in added.items():
        append_section(lines, section, rows, ending)
    derived = ''.join(lines).encode()
    require(len(derived) <= 2_000_000, 'STORAGE_DESIGN_INPUT_TOO_LARGE')
    return derived, {'schemaVersion': 1, 'method': METHOD, 'source': SOURCE,
        'sourceNetworkSha256': digest(raw), 'derivedNetworkSha256': digest(derived),
        'compilerSha256': digest(Path(__file__).read_bytes()), 'design': deepcopy(design), 'facilities': details,
        'rankingEligible': False, 'historicalReconstructionEligible': False,
        'limitations': ['명시적 설계 제원이며 현장 치수·입지·공사 가능성·단가의 검증 아님',
            '기존 절점과 시설 사이의 국부 오리피스 연결; 긴 접속관 마찰·침전·막힘은 포함하지 않음',
            '덮개·차수 설계의 지하 저장 범위; 개방 저류지 직접 강우·증발·침투와 구분',
            '비상 배수구 용량 초과 시 별도 지표 연결이 필요하며 절점 월류 소실은 성공 효과 아님']}


def storage_ledger(metadata, origin, final):
    from .cistern_inlet import inlet_ledger
    from .cistern_outlet import outlet_ledgers
    start, end = origin['totals']['timeSeconds'], final['totals']['timeSeconds']
    require(0 <= start < end, 'STORAGE_LEDGER_CLOCK_INVALID')
    rows = []
    for design in metadata['facilities']:
        name = design['nodeId']
        require(name in origin['nodes'] and name in final['nodes'], 'STORAGE_LEDGER_NODE_MISSING')
        before, after = origin['nodes'][name], final['nodes'][name]
        require(before['type'] == after['type'] == 2, 'STORAGE_LEDGER_NODE_TYPE_INVALID')
        incoming = after['statisticInflowIncludingInitialM3']-before['statisticInflowIncludingInitialM3']
        outgoing = after['statisticOutflowM3']-before['statisticOutflowM3']
        flooding = after['floodingM3']-before['floodingM3']
        initial, stored = before['storageM3'], after['storageM3']
        native_capacity = design.get('nativeCapacityM3', design['capacityM3'])
        require(all(math.isfinite(v) and v >= -1e-9 for v in (incoming, outgoing, flooding, initial, stored)),
                'STORAGE_LEDGER_COUNTER_INVALID')
        residual = initial+incoming-outgoing-stored
        tolerance = max(1e-8, .01*max(initial+incoming, outgoing+stored))
        # 엔진 절점 유출 누적량에 월류가 이미 포함되므로 다시 합산하지 않는다.
        item = {'id': design['id'], 'nodeId': name, 'initialStorageM3': initial,
            'inflowM3': incoming, 'outflowIncludingFloodingM3': outgoing, 'floodingM3': flooding,
            'finalStorageM3': stored, 'capacityM3': design['capacityM3'],
            'balanceResidualM3': residual, 'allowedResidualM3': tolerance,
            'numericalStatus': 'PASSED' if abs(residual) <= tolerance
                and flooding <= 1e-9 and max(initial, stored) <= native_capacity+1e-8 else 'FAILED'}
        if 'nativeCapacityM3' in design:
            item.update(nativeCapacityM3=native_capacity, volumeBasis=design['volumeBasis'],
                        initialAvailableM3=native_capacity-initial, finalAvailableM3=native_capacity-stored)
        if design.get('facilityType') == 'RAINWATER_CISTERN':
            item.update(reuseM3=None, reuseStatus='NOT_CALCULATED_NO_USE_DEMAND',
                        drainOperation=metadata.get('drainOperation', 'GRAVITY_ORIFICE'))
        rows.append(item)
    inlet = inlet_ledger(metadata, origin, final)
    outlets = outlet_ledgers(metadata, origin, final)
    return {'startSeconds': start, 'endSeconds': end, 'facilities': rows,
        **({'inletPipe': inlet} if inlet else {}),
        **({'outletPipes': outlets} if outlets else {}),
        'scope': 'NATIVE_STORAGE_NODE_BALANCE_ALREADY_INCLUDED_IN_NETWORK_ROUTING',
        'numericalStatus': 'PASSED' if all(row['numericalStatus'] == 'PASSED' for row in rows)
            and (inlet is None or inlet['numericalStatus'] == 'PASSED')
            and all(pipe['numericalStatus'] == 'PASSED' for pipe in outlets.values()) else 'FAILED'}


def result_summary(metadata, initial, final, evaluation_origin=None):
    whole = storage_ledger(metadata, initial, final)
    evaluation = storage_ledger(metadata, evaluation_origin, final) if evaluation_origin is not None else None
    return {'design': metadata, 'wholeRunLedger': whole, 'evaluationLedger': evaluation,
        'numericalStatus': 'PASSED' if whole['numericalStatus'] == 'PASSED'
            and (evaluation is None or evaluation['numericalStatus'] == 'PASSED') else 'FAILED',
        'routingBalanceAlreadyIncludesStorageAndFlows': True, 'rankingEligible': False}
