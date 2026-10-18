"""공개 성능곡선과 명시적 압력관 설계를 기존 관망에 연결."""
from collections import defaultdict, deque
from copy import deepcopy
import json
import math
import re
from pathlib import Path

from .swmm import ROOT
from .flood_errors import require
from .connected_storage import indexed, identifier, number, append_section
from ..ingestion.published_network import records, digest

CATALOG = ROOT/'data/derived/pump-curves/ksb-pa4-500-270-1450-17-v1.json'
CATALOG_HASH = 'f27bbf2baeb0c07848539aaf944c7771e0f391ee7c864166f2c646d180f5dde8'


def catalog():
    raw = CATALOG.read_bytes()
    require(digest(raw) == CATALOG_HASH, 'PUMP_CURVE_SOURCE_CHANGED')
    return json.loads(raw)


def compile_pumps(raw, design):
    curve = catalog()
    require(isinstance(design, dict) and set(design) == {
        'schemaVersion', 'sourceNetworkSha256', 'curveCatalogHash', 'placements'}
        and type(design['schemaVersion']) is int and design['schemaVersion'] == 1
        and design['sourceNetworkSha256'] == digest(raw) and design['curveCatalogHash'] == CATALOG_HASH,
        'PUMP_DESIGN_SOURCE_INVALID')
    require(isinstance(design['placements'], list) and 0 < len(design['placements']) <= 20,
        'PUMP_DESIGN_PLACEMENTS_INVALID')
    text, sections = records(raw)
    options = indexed(sections.get('OPTIONS', []))
    require(all(len(v) == 2 for v in options.values()), 'PUMP_DESIGN_OPTIONS_INVALID')
    require(options.get('FLOW_UNITS', ['', ''])[1].upper() == 'CMS'
        and options.get('FLOW_ROUTING', ['', ''])[1].upper() == 'DYNWAVE'
        and options.get('LINK_OFFSETS', ['', 'DEPTH'])[1].upper() == 'DEPTH', 'PUMP_DESIGN_SI_DYNWAVE_REQUIRED')
    has_force_main = any(r['tokens'][1].upper() == 'FORCE_MAIN' for r in sections.get('XSECTIONS', []))
    require(not has_force_main or options.get('FORCE_MAIN_EQUATION', ['', 'H-W'])[1].upper() == 'D-W',
        'PUMP_DESIGN_FORCE_MAIN_CONFLICT')
    nodes = indexed([r for s in ('JUNCTIONS', 'STORAGE', 'OUTFALLS', 'DIVIDERS') for r in sections.get(s, [])])
    internal = indexed(sections.get('JUNCTIONS', []) + sections.get('STORAGE', []))
    links = indexed([r for s in ('CONDUITS', 'PUMPS', 'ORIFICES', 'WEIRS', 'OUTLETS') for r in sections.get(s, [])])
    outfalls = set(indexed(sections.get('OUTFALLS', [])))
    reserved = {t.upper() for rows in sections.values() for r in rows for t in r['tokens']}
    graph = defaultdict(set)
    for row in links.values():
        require(len(row) >= 3 and all(n.upper() in nodes for n in row[1:3]), 'PUMP_DESIGN_SOURCE_LINK_INVALID')
        graph[row[1].upper()].add(row[2].upper())
    def reachable(node):
        found, queue = {node}, deque([node])
        while queue:
            for nxt in graph[queue.popleft()]-found:
                found.add(nxt); queue.append(nxt)
        return found
    added = {s: [] for s in ('OPTIONS', 'JUNCTIONS', 'PUMPS', 'CONDUITS', 'XSECTIONS', 'LOSSES', 'CURVES')}
    if 'FORCE_MAIN_EQUATION' not in options: added['OPTIONS'] = ['FORCE_MAIN_EQUATION D-W']
    details, used, pairs = [], set(), set()
    for p in design['placements']:
        require(isinstance(p, dict) and set(p) == {'id', 'facilityType', 'basis', 'evidence', 'curveId',
            'fromNode', 'toNode', 'startDepthM', 'stopDepthM', 'initialStatus', 'delivery'},
            'PUMP_DESIGN_PLACEMENT_INVALID')
        require(p['facilityType'] == 'PUMP_STATION' and p['basis'] == 'EXPLICIT_DESIGN_NOT_SITE_MEASURED'
            and isinstance(p['evidence'], str) and 1 <= len(p['evidence']) <= 500
            and p['curveId'] == curve['id'], 'PUMP_DESIGN_EVIDENCE_INVALID')
        name = 'WLPU_'+identifier(p['id'])
        generated = {name.upper()} | {(name+'_'+suffix).upper() for suffix in ('D', 'F', 'H', 'P', 'N')}
        require(not generated.intersection(reserved | used), 'PUMP_DESIGN_ID_COLLISION')
        used |= generated
        source, receiver = (identifier(p[k], source=True).upper() for k in ('fromNode', 'toNode'))
        require(source in internal and receiver in internal and source != receiver
            and receiver in reachable(source) and reachable(receiver) & outfalls,
            'PUMP_DESIGN_EXISTING_DOWNSTREAM_REQUIRED')
        require((source, receiver) not in pairs, 'PUMP_DESIGN_DUPLICATE_CONNECTION')
        pairs.add((source, receiver))
        stop = number(p['stopDepthM'], high=float(nodes[source][2]), positive=True)
        start = number(p['startDepthM'], high=float(nodes[source][2]), positive=True)
        require(start > stop and p['initialStatus'] in ('ON', 'OFF'), 'PUMP_DESIGN_CONTROL_INVALID')
        pipe = p['delivery']
        require(isinstance(pipe, dict) and set(pipe) == {'lengthM', 'diameterM', 'roughnessMm',
            'pressureHeadLimitM', 'entranceLoss', 'exitLoss', 'averageLoss', 'checkValve', 'evidence'},
            'PUMP_DESIGN_DELIVERY_INVALID')
        length = number(pipe['lengthM'], high=10000, positive=True)
        diameter = number(pipe['diameterM'], high=20, positive=True)
        roughness = number(pipe['roughnessMm'], high=100, positive=True)
        require(roughness < diameter*1000, 'PUMP_DESIGN_ROUGHNESS_INVALID')
        # EPA forcmain.c의 완전 난류 등가 n. 관 입력의 양수 검사를 충족하며 엔진이 같은 식으로 재산정한다.
        friction = .25/math.log10(roughness/1000/diameter/3.7)**2
        manning = math.sqrt(friction/185)*(diameter/.3048)**(1/6)
        pressure = number(pipe['pressureHeadLimitM'], high=1000, positive=True)
        losses = [number(pipe[k], high=100) for k in ('entranceLoss', 'exitLoss', 'averageLoss')]
        require(pressure > diameter and isinstance(pipe['evidence'], str) and 1 <= len(pipe['evidence']) <= 500,
            'PUMP_DESIGN_DELIVERY_EVIDENCE_INVALID')
        require(type(pipe['checkValve']) is bool, 'PUMP_DESIGN_CHECK_VALVE_INVALID')
        origin, target = nodes[source][0], nodes[receiver][0]
        invert = float(nodes[receiver][1])
        added['JUNCTIONS'].append(f'{name}_D {invert:.15g} {diameter:.15g} 0 {pressure-diameter:.15g} 0')
        added['PUMPS'].append(f'{name} {origin} {name}_D {name}_H {p["initialStatus"]} {start:.15g} {stop:.15g}')
        # FORCE_MAIN의 마찰은 관 단면의 절대조도와 D-W 식으로 계산한다.
        added['CONDUITS'].append(f'{name}_F {name}_D {target} {length:.15g} {manning:.15g} 0 0 0 0')
        added['XSECTIONS'].append(f'{name}_F FORCE_MAIN {diameter:.15g} {roughness:.15g} 0 0 1')
        added['LOSSES'].append(f'{name}_F '+ ' '.join(f'{v:.15g}' for v in losses)
                               + (' YES 0' if pipe['checkValve'] else ' NO 0'))
        for i, point in enumerate(reversed(curve['points'])):
            added['CURVES'].append(f'{name}_H {"PUMP3 " if i == 0 else ""}{point["headM"]:.15g} {point["flowM3h"]/3600:.15g}')
        for suffix, key in (('P', 'shaftPowerKw'), ('N', 'npshRequiredM')):
            for i, point in enumerate(curve['points']):
                added['CURVES'].append(f'{name}_{suffix} {"CONTROL " if i == 0 else ""}{point["flowM3h"]/3600:.15g} {point[key]:.15g}')
        details.append({'id': p['id'], 'linkId': name, 'deliveryNodeId': name+'_D',
            'deliveryLinkId': name+'_F', 'fromNode': origin, 'toNode': target,
            'curveId': curve['id'], 'flowRangeM3s': [curve['points'][0]['flowM3h']/3600, curve['points'][-1]['flowM3h']/3600],
            'headRangeM': [curve['points'][-1]['headM'], curve['points'][0]['headM']],
            'frequencyHz': curve['frequencyHz'], 'speedRpm': curve['speedRpm'],
            'startDepthM': start, 'stopDepthM': stop, 'delivery': deepcopy(pipe),
            'equivalentManning': manning, 'equivalentManningBasis': 'EPA_FORCMAIN_D_W_FULLY_TURBULENT',
            'headReference': curve['headReference']})
    ending = '\r\n' if '\r\n' in text else '\n'
    lines = text.splitlines(keepends=True)
    for row in sections.get('OPTIONS', []):
        if row['tokens'][0].upper() == 'FORCE_MAIN_EQUATION':
            i = row['line']-1
            lines[i] = re.sub(r'(?i)(FORCE_MAIN_EQUATION\s+)\S+', r'\g<1>D-W', lines[i], count=1)
    for section, rows in added.items():
        if rows: append_section(lines, section, rows, ending)
    derived = ''.join(lines).encode()
    require(len(derived) <= 2_000_000, 'PUMP_DESIGN_INPUT_TOO_LARGE')
    return derived, {'schemaVersion': 1, 'method': 'PUBLIC_PUMP3_DARCY_WEISBACH_DELIVERY_V1',
        'sourceNetworkSha256': digest(raw), 'derivedNetworkSha256': digest(derived),
        'compilerSha256': digest(Path(__file__).read_bytes()), 'curveCatalogHash': CATALOG_HASH,
        'forceMainEquation': {'original': options.get('FORCE_MAIN_EQUATION', [None, None])[1],
                             'applied': 'D-W', 'existingForceMains': has_force_main},
        'design': deepcopy(design), 'facilities': details, 'rankingEligible': False,
        'historicalReconstructionEligible': False, 'completeInstalledCostKrw': None,
        'limitations': curve['limitations'] + ['신규 설계 펌프와 접속관이며 실제 서울 시설·입지·관로의 확인 아님',
            '관망 동역학 범위이며 기동 관성·수격·공기 혼입·펌프 마모·고장 미계산',
            '압력관은 수신 절점 바닥과 같은 기준고의 수평 접속 설계; 현장 종단 측량 아님',
            'SWMM 5.2.4 D-W의 동점성은 20°C 상수 1.1e-5ft²/s이며 관측 수온별 보정 없음',
            '흡입관과 제조사 기준면 이후 토출관의 손실을 명시적 설계에 반영해야 하며 현장 계수 미검증',
            'NPSHr만 계산하며 NPSHa·잠김 조건 미확보로 캐비테이션 안전 판정 없음',
            '펌프 유량은 내부 이송량이며 외부 유출·침수 감소량과 별도']}
