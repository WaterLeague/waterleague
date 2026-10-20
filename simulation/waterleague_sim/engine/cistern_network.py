"""강우 면적을 보존한 집수 분할과 수두 지배 이용조 배수 연결."""
from copy import deepcopy
import math
from pathlib import Path

from .connected_storage import append_section, capacity, identifier, indexed, number, SOURCE, volume_properties
from .flood_errors import require
from ..ingestion.published_network import digest, records

METHOD = 'COVERED_CISTERN_IMPERVIOUS_CAPTURE_DYNWAVE_V1'
MIXED_METHOD = 'COVERED_CISTERN_MIXED_SURFACE_CAPTURE_DYNWAVE_V2'
SHARED_METHOD = 'COVERED_CISTERN_DISJOINT_COVER_CAPTURE_DYNWAVE_V3'


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
        and type(design['schemaVersion']) is int and design['schemaVersion'] in (1, 2, 3)
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
    require(len(host) in (8, 9) and (len(host) == 8 or host[8] == '*'),
        'CISTERN_SOURCE_CATCHMENT_INVALID')
    impervious_percent = source_number(host[4])
    split_cover = design['schemaVersion'] == 3
    mixed = design['schemaVersion'] == 2 or (split_cover and impervious_percent < 100)
    require((0 < impervious_percent < 100) if mixed else impervious_percent == 100,
        'CISTERN_MIXED_HOST_REQUIRED' if mixed else 'CISTERN_FULLY_IMPERVIOUS_HOST_REQUIRED')
    require(all(len(row) >= 3 for row in catchments.values()), 'CISTERN_SOURCE_CATCHMENT_INVALID')
    # 추가 수문 상태·상류 유입은 독립 표면 분할로 재배분하지 않는다.
    for section in ('LID_USAGE', 'GROUNDWATER', 'GWF', 'COVERAGES', 'LOADINGS'):
        require(not any(row['tokens'][0].upper() == host_id for row in sections.get(section, [])),
                'CISTERN_HOST_ADDITIONAL_PROCESS_UNSUPPORTED')
    require(not sections.get('POLLUTANTS') and not sections.get('AQUIFERS'),
            'CISTERN_SOURCE_ADDITIONAL_PROCESS_UNSUPPORTED')
    require(not any(row[2].upper() == host_id for row in catchments.values()),
            'CISTERN_UPSTREAM_RUNON_UNSUPPORTED')
    if mixed or split_cover:
        require(not sections.get('FILES'), 'CISTERN_EXTERNAL_STATE_UNSUPPORTED')
        require(not any(len(r['tokens']) > 9 and r['tokens'][9].upper() == host_id
            for r in sections.get('LID_USAGE', [])), 'CISTERN_UPSTREAM_RUNON_UNSUPPORTED')
        for r in sections.get('OUTFALLS', []):
            tokens = r['tokens']
            route_index = 4 if len(tokens) > 2 and tokens[2].upper() in ('FREE', 'NORMAL') else 5
            require(not (len(tokens) > route_index and tokens[route_index].upper() == host_id),
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
    impervious = area * impervious_percent / 100 if mixed else area
    capture = number(design['captureAreaM2'], positive=True)
    footprint = number(design['footprintM2'], positive=True)
    require(capture + footprint <= impervious, 'CISTERN_CAPTURE_FOOTPRINT_OVERLAP')
    if split_cover:
        require(capture + footprint < impervious, 'CISTERN_SHARED_CATCHMENT_REMAINDER_REQUIRED')
    volume = capacity(design['depthAreaCurve'])
    require(max(p['areaM2'] for p in design['depthAreaCurve']) <= footprint,
            'CISTERN_STORAGE_EXCEEDS_FOOTPRINT')
    depth = design['depthAreaCurve'][-1]['depthM']
    invert = number(design['invertM'], -1000, 10000)
    initial = number(design['initialDepthM'], high=depth)
    name = 'WLCT_' + identifier(design['id'])
    child, curve, bypass, cover = name + '_C', name + '_A', name + '_B', name + '_R'
    names = {name.upper(), child.upper(), curve.upper(), (name+'_D').upper(), (name+'_O').upper()}
    if mixed: names.add(bypass.upper())
    if split_cover: names.add(cover.upper())
    existing = {t.upper() for rows in sections.values() for r in rows for t in r['tokens']}
    require(not names.intersection(existing), 'CISTERN_ID_COLLISION')
    added = {'SUBCATCHMENTS': [], 'SUBAREAS': [], 'INFILTRATION': [], 'STORAGE': [],
             'CURVES': [], 'ORIFICES': [], 'XSECTIONS': []}
    remaining = host[:]
    remaining[3], remaining[5] = format((area-capture)/10000, '.15g'), format(width*(area-capture)/area, '.15g')
    diverted = host[:]
    diverted[0:3] = [child, host[1], name]
    diverted[3], diverted[5] = format(capture/10000, '.15g'), format(width*capture/area, '.15g')
    if mixed:
        # SWMM은 투수·불투수 각각의 면적에 같은 원 폭을 사용한다. 세 표면을 분리해야 두 유출 계수가 보존된다.
        remaining[3:6] = [format((area-impervious)/10000, '.15g'), '0', host[5]]
        diverted[4:6] = ['100', format(width*capture/impervious, '.15g')]
        bypass_row = host[:]
        bypass_row[0] = bypass
        bypass_row[3:6] = [format((impervious-capture)/10000, '.15g'), '100',
            format(width*(impervious-capture)/impervious, '.15g')]
        if split_cover:
            bypass_row[3:6] = [format((impervious-capture-footprint)/10000, '.15g'), '100',
                format(width*(impervious-capture-footprint)/impervious, '.15g')]
        added['SUBCATCHMENTS'].append(' '.join(bypass_row))
        added['SUBAREAS'].append(' '.join([bypass, *subareas[host_id][1:]]))
    if split_cover:
        # 덮개를 독립 표면으로 분리해 다른 LID가 덮개 강우까지 포집하지 않게 한다.
        if not mixed:
            remaining[3:6] = [format((area-capture-footprint)/10000, '.15g'), '100',
                format(width*(area-capture-footprint)/area, '.15g')]
        cover_row = host[:]
        cover_row[0] = cover
        cover_row[3:6] = [format(footprint/10000, '.15g'), '100', format(width*footprint/impervious, '.15g')]
        added['SUBCATCHMENTS'].append(' '.join(cover_row))
        added['SUBAREAS'].append(' '.join([cover, *subareas[host_id][1:]]))
    added['SUBCATCHMENTS'].append(' '.join(diverted))
    added['SUBAREAS'].append(' '.join([child, *subareas[host_id][1:]]))
    infiltration = indexed(sections.get('INFILTRATION', []))
    if host_id in infiltration:
        added['INFILTRATION'].append(' '.join([child, *infiltration[host_id][1:]]))
        if mixed:
            added['INFILTRATION'].append(' '.join([bypass, *infiltration[host_id][1:]]))
        if split_cover:
            added['INFILTRATION'].append(' '.join([cover, *infiltration[host_id][1:]]))
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
    # 원 행 외의 수문 입력·배수 연결과 주석은 유지한다.
    comment = lines[row['line']-1].split(';', 1)
    lines[row['line']-1] = ' '.join(remaining) + (' ;'+comment[1].rstrip('\r\n') if len(comment)>1 else '') + ending
    for section, rows in added.items():
        if rows: append_section(lines, section, rows, ending)
    result = ''.join(lines).encode()
    require(len(result) <= 2_000_000, 'CISTERN_INPUT_TOO_LARGE')
    partition = {'hostId': host[0], 'captureId': child, 'originalAreaM2': area,
        'bypassAreaM2': area-capture, 'captureAreaM2': capture, 'coverAreaM2': footprint,
        'originalWidthM': width, 'bypassWidthM': float(remaining[5]), 'captureWidthM': float(diverted[5]),
        'coverRainfallRoute': 'BYPASS_CATCHMENT_TO_ORIGINAL_OUTLET', 'rainfallCount': 1,
        'captureBasis': 'EXPLICIT_DESIGN_UNIFORM_IMPERVIOUS_PARTITION_NOT_MEASURED_ROOF'}
    limitations = ['전면 불투수 집수의 명시적 균질 분할; 실제 지붕·홈통 연결 관측 아님',
        '기존 강우 면적·조도·요지저류·폭/면적 보존, 덮개 강우는 원 출구로 우회',
        '집수 유출은 이용조 측방 유입으로 연결; 홈통 용량·막힘·역류의 지붕 재유입 미모형화',
        '배수·비상구의 관망 수두 및 역류 반영; 접속관 마찰은 별도 설계 필요',
        '포화 토양·수질·수요·펌프 없는 재이용 저감점수 부여 금지',
        '비상구 용량 초과에 따른 이용조 절점 월류는 실패로 보존']
    if mixed:
        partition.update({'imperviousBypassId': bypass, 'originalImperviousPercent': impervious_percent,
            'originalImperviousAreaM2': impervious, 'preservedPerviousAreaM2': area-impervious,
            'imperviousBypassAreaM2': impervious-capture, 'bypassWidthM': None,
            'perviousWidthM': width, 'imperviousBypassWidthM': float(bypass_row[5]),
            'widthBasis': 'PRESERVE_SWMM_ALPHA_WIDTH_PER_SURFACE_AREA'})
        limitations[0] = '원 투수면을 보존하고 불투수면만 명시적으로 분할; 실제 지붕·홈통 연결 관측 아님'
        limitations[1] = '투수/불투수별 강우 면적·조도·요지저류·유출 계수와 원 침투 입력 보존; 덮개 강우는 원 출구로 우회'
    if split_cover:
        partition.update({'coverId': cover, 'coverWidthM': float(cover_row[5]),
            'imperviousBypassId': bypass if mixed else host[0],
            'originalImperviousAreaM2': impervious, 'preservedPerviousAreaM2': area-impervious,
            'imperviousBypassAreaM2': impervious-capture-footprint,
            'imperviousBypassWidthM': float(bypass_row[5] if mixed else remaining[5]),
            'coverRainfallRoute': 'DEDICATED_COVER_CATCHMENT_TO_ORIGINAL_OUTLET',
            'widthBasis': 'PRESERVE_SWMM_ALPHA_WIDTH_PER_SURFACE_AREA'})
        limitations.append('덮개·이용조 집수를 제외한 불투수 우회면만 다른 LID 배분 가능; 시설 배수 재포집 없음')
    method = SHARED_METHOD if split_cover else MIXED_METHOD if mixed else METHOD
    return result, {'schemaVersion': design['schemaVersion'], 'method': method, 'source': SOURCE,
        'sourceNetworkSha256': digest(raw), 'derivedNetworkSha256': digest(result),
        'compilerSha256': digest(Path(__file__).read_bytes()), 'design': deepcopy(design),
        'catchmentPartition': partition,
        'facilities': [{'id': design['id'], 'nodeId': name, 'facilityType': 'RAINWATER_CISTERN',
            'capacityM3': volume, **volume_properties(volume), 'ports': ports, 'directRainfallM3': 0, 'evaporationFactor': 0,
            'seepageMmH': 0, 'surfaceOwnership': 'COVER_RETAINS_ORIGINAL_IMPERVIOUS_BYPASS',
            'geometryVerifiedOnSite': False}],
        'rankingEligible': False, 'historicalReconstructionEligible': False,
        'limitations': limitations}
