"""기존 도로·개수로와 관망 사이의 EPA 격자 유입부 설계."""
from collections import defaultdict
from copy import deepcopy
from pathlib import Path

from .connected_storage import append_section, identifier, indexed, number
from .flood_errors import require
from ..ingestion.published_network import digest, records

GRATES = ('P_BAR-50', 'P_BAR-50x100', 'P_BAR-30', 'CURVED_VANE',
          'TILT_BAR-45', 'TILT_BAR-30', 'RETICULINE')
SOURCE = {'title': 'EPA SWMM 5.2 User Manual',
    'url': 'https://www.epa.gov/system/files/documents/2022-04/swmm-users-manual-version-5.2.pdf',
    'sections': ['3.3.7 Inlet Drains', '[INLETS]', '[INLET_USAGE]'],
    'engineRevision': '7952ca837988b1c32f791812eccc9fd64547e093'}


def compile_inlets(raw, design):
    text, sections = records(raw)
    require(isinstance(design, dict) and set(design) == {'schemaVersion', 'sourceNetworkSha256', 'placements'}
        and type(design['schemaVersion']) is int and design['schemaVersion'] == 1
        and design['sourceNetworkSha256'] == digest(raw), 'INLET_SOURCE_BINDING_INVALID')
    placements = design['placements']
    require(isinstance(placements, list) and 0 < len(placements) <= 128, 'INLET_PLACEMENTS_INVALID')
    options = indexed(sections.get('OPTIONS', []))
    require(options.get('FLOW_UNITS', ['', ''])[1].upper() == 'CMS'
        and options.get('FLOW_ROUTING', ['', ''])[1].upper() == 'DYNWAVE', 'INLET_SI_DYNWAVE_REQUIRED')
    channels = indexed(sections.get('CONDUITS', []))
    shapes = indexed(sections.get('XSECTIONS', []))
    nodes = indexed(sections.get('JUNCTIONS', [])+sections.get('STORAGE', []))
    outfalls = indexed(sections.get('OUTFALLS', []))
    streets = indexed(sections.get('STREETS', []))
    used = {token.upper() for rows in sections.values() for row in rows for token in row['tokens']}
    occupied = set(indexed(sections.get('INLET_USAGE', [])))
    graph = defaultdict(set)
    for section in ('CONDUITS', 'PUMPS', 'ORIFICES', 'WEIRS', 'OUTLETS'):
        for row in sections.get(section, []):
            t = row['tokens']; graph[t[1].upper()].add(t[2].upper())
    def reachable(start):
        seen, todo = set(), {start}
        while todo:
            current = todo.pop(); seen.add(current); todo.update(graph[current]-seen)
        return seen
    added, usage, details = [], [], []
    for p in placements:
        require(isinstance(p, dict) and set(p) == {'id', 'facilityType', 'basis', 'evidence',
            'conduitId', 'captureNodeId', 'shape', 'numberPerSide', 'cloggedPercent',
            'flowLimitM3s', 'localDepressionM', 'localWidthM', 'placement'}, 'INLET_PLACEMENT_INVALID')
        require(p['facilityType'] == 'STORM_INLET' and p['basis'] == 'EXPLICIT_DESIGN_NOT_SITE_MEASURED'
            and isinstance(p['evidence'], str) and p['evidence'].strip(), 'INLET_EVIDENCE_REQUIRED')
        name = 'WLIN_'+identifier(p['id'])
        channel = identifier(p['conduitId'], source=True).upper()
        target = identifier(p['captureNodeId'], source=True).upper()
        require(name.upper() not in used and channel not in occupied, 'INLET_DUPLICATE_OR_COLLISION')
        require(channel in channels and channel in shapes and target in nodes,
                'INLET_EXISTING_CHANNEL_AND_CAPTURE_NODE_REQUIRED')
        shape = p['shape']
        require(isinstance(shape, dict) and set(shape) == {'type', 'lengthM', 'widthM', 'grateType'}
            and shape['type'] in ('GRATE', 'DROP_GRATE') and shape['grateType'] in GRATES,
            'INLET_SHAPE_INVALID')
        xsection = shapes[channel]
        if shape['type'] == 'GRATE':
            require(xsection[1].upper() == 'STREET' and len(xsection) >= 3
                    and xsection[2].upper() in streets, 'INLET_STREET_PROFILE_REQUIRED')
        else:
            require(xsection[1].upper() in ('RECT_OPEN', 'TRAPEZOIDAL'), 'INLET_OPEN_CHANNEL_REQUIRED')
        source_nodes = {v.upper() for v in channels[channel][1:3]}
        require(source_nodes <= set(nodes) and target not in source_nodes
            and reachable(target) & set(outfalls), 'INLET_CONNECTED_CAPTURE_REQUIRED')
        # 유입 지점에서 원 지표 경로로 다시 연결되는 순환 설계는 명시적 검증 전 거부한다.
        require(not reachable(target).intersection(source_nodes), 'INLET_CAPTURE_SURFACE_LOOP')
        require(not any(target in {v.upper() for v in row[1:3]}
            and shapes.get(key, ['', ''])[1].upper() in ('STREET', 'RECT_OPEN', 'TRAPEZOIDAL')
            for key, row in channels.items()), 'INLET_CAPTURE_SEWER_REQUIRED')
        length, width = [number(shape[k], high=100, positive=True) for k in ('lengthM', 'widthM')]
        require(length <= number(float(channels[channel][3]), positive=True), 'INLET_LENGTH_EXCEEDS_CHANNEL')
        available_width = float(streets[xsection[2].upper()][1]) if shape['type'] == 'GRATE' else float(xsection[3])
        require(width <= available_width, 'INLET_WIDTH_EXCEEDS_CHANNEL')
        count = p['numberPerSide']
        require(type(count) is int and 1 <= count <= 100 and p['placement'] in ('ON_GRADE', 'ON_SAG'),
                'INLET_PLACEMENT_MODE_INVALID')
        clogged = number(p['cloggedPercent'], high=99)
        flow = number(p['flowLimitM3s'], high=10000)
        depression = number(p['localDepressionM'], high=10)
        local_width = number(p['localWidthM'], high=100)
        require(depression == 0 or local_width > 0, 'INLET_DEPRESSION_WIDTH_REQUIRED')
        require(shape['type'] == 'GRATE' or depression == local_width == 0, 'INLET_DROP_DEPRESSION_CONFLICT')
        used.add(name.upper()); occupied.add(channel)
        added.append(f'{name} {shape["type"]} {length:.15g} {width:.15g} {shape["grateType"]}')
        usage.append(f'{channels[channel][0]} {name} {nodes[target][0]} {count} {clogged:.15g} '
            f'{flow:.15g} {depression:.15g} {local_width:.15g} {p["placement"]}')
        details.append({'id': p['id'], 'designId': name, 'conduitId': channels[channel][0],
            'bypassNodeId': channels[channel][2], 'captureNodeId': nodes[target][0],
            'design': deepcopy(p), 'geometryVerifiedOnSite': False})
    ending = '\r\n' if '\r\n' in text else '\n'
    lines = text.splitlines(keepends=True)
    append_section(lines, 'INLETS', added, ending)
    append_section(lines, 'INLET_USAGE', usage, ending)
    derived = ''.join(lines).encode()
    require(len(derived) <= 2_000_000, 'INLET_INPUT_TOO_LARGE')
    return derived, {'schemaVersion': 1, 'method': 'EPA_HEC22_EXISTING_CHANNEL_INLETS_V1',
        'source': SOURCE, 'sourceNetworkSha256': digest(raw), 'derivedNetworkSha256': digest(derived),
        'compilerSha256': digest(Path(__file__).read_bytes()), 'design': deepcopy(design), 'facilities': details,
        'rankingEligible': False, 'completeInstalledCostKrw': None,
        'limitations': ['도로·개수로 단면과 연결은 원 입력 유지; 유입부 치수·막힘·배치는 명시적 설계',
            'HEC-22 격자 제원은 공개 참고 유형이며 서울 현장 설치 제품 확인 아님',
            'TILT_BAR-45의 개구율 0.17은 EPA 원 코드의 가정값',
            'EPA 하수관 월류 배분에 의한 지표 반환이며 2D 지표와 관망의 수두 결합 아님',
            '내부 포착·반환 체적은 외부 배수 또는 침수 저감량에 합산하지 않음']}
