"""원 지형을 보존한 개방 저류지 절토와 관망 교환 입력."""
from collections import defaultdict
from copy import deepcopy
import hashlib
import math
from pathlib import Path

from waterleague_sim.engine.connected_storage import append_section, identifier, indexed, number
from waterleague_sim.engine.flood_errors import require
from waterleague_sim.engine.surface_infiltration import validate as validate_soil
from waterleague_sim.evaluation.values import digest
from waterleague_sim.ingestion.published_network import records

METHOD = 'EXPLICIT_SURFACE_BASIN_EARTHWORK_V1'


def triangle_area(surface, cell):
    a, b, c = [surface['verticesM'][i] for i in surface['triangles'][cell]]
    return ((b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]))/2


def material(source, cells, design, owners):
    require(isinstance(design, dict) and set(design) == {'manningN', 'lining', 'soil', 'evidence'}
            and design['lining'] in ('SEALED', 'PERMEABLE') and design['evidence'],
            'BASIN_MATERIAL_REQUIRED')
    roughness = number(design['manningN'], high=1, positive=True)
    value = deepcopy(validate_soil(source, owners))
    if value['schemaVersion'] == 1:
        value['schemaVersion'] = 2
        value['partitionPolicy'] = 'EXPLICIT_AREA_FRACTIONS'
        value['imperviousRegions'] = []
        sealed = value.pop('imperviousTriangles')
        if sealed:
            value['imperviousRegions'].append({'triangles': sealed, 'areaFraction': 1., 'evidence': value['evidence']})
        for row in value['regions']:
            if row['perviousFraction'] < 1:
                value['imperviousRegions'].append({'triangles': row['triangles'][:],
                    'areaFraction': 1-row['perviousFraction'], 'evidence': row['evidence']})
    for key in ('regions', 'imperviousRegions'):
        rows = []
        for row in value[key]:
            row['triangles'] = [i for i in row['triangles'] if i not in cells]
            if row['triangles']:
                rows.append(row)
        value[key] = rows
    if design['lining'] == 'SEALED':
        require(design['soil'] is None, 'BASIN_SEALED_SOIL_CONFLICT')
        value['imperviousRegions'].append({'triangles': sorted(cells), 'areaFraction': 1.,
                                          'evidence': design['evidence']})
    else:
        soil = design['soil']
        require(isinstance(soil, dict) and set(soil) == {
            'suctionMm', 'conductivityMmH', 'initialMoistureDeficit'}, 'BASIN_SOIL_PARAMETERS_REQUIRED')
        value['regions'].append({'triangles': sorted(cells), 'perviousFraction': 1.,
                                'evidence': design['evidence'], **soil})
    return roughness, validate_soil(value, owners)


def compile_basin(model):
    source = deepcopy(model)
    design = source.pop('surfaceBasinDesign')
    require(isinstance(design, dict) and set(design) == {'schemaVersion', 'sourceModelSha256', 'placements'}
        and type(design['schemaVersion']) is int and design['schemaVersion'] == 1
        and design['sourceModelSha256'] == digest(source), 'BASIN_SOURCE_BINDING_INVALID')
    require('connectedStorageDesign' not in source, 'BASIN_STORAGE_COMPOSITION_NOT_SUPPORTED')
    placements = design['placements']
    require(isinstance(placements, list) and 0 < len(placements) <= 128, 'BASIN_PLACEMENTS_INVALID')
    surface = source['surface']
    require(surface.get('schemaVersion') == 2 and surface.get('infiltration') is not None
        and surface.get('evaporation') is not None and source.get('evaluationMetrics') is not None,
        'BASIN_WATER_BALANCE_INPUT_REQUIRED')
    original = deepcopy(surface)
    size = len(surface['triangles'])
    edges, adjacency = defaultdict(list), defaultdict(set)
    for i, tri in enumerate(surface['triangles']):
        require(triangle_area(surface, i) > 0, 'BASIN_MESH_INVALID')
        for a, b in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
            edges[tuple(sorted((a, b)))].append(i)
    require(all(len(rows) <= 2 for rows in edges.values()), 'BASIN_MESH_INVALID')
    for rows in edges.values():
        if len(rows) == 2:
            adjacency[rows[0]].add(rows[1]); adjacency[rows[1]].add(rows[0])
    text, sections = records(source['network']['inputText'].encode())
    options = indexed(sections.get('OPTIONS', []))
    require(options.get('FLOW_UNITS', ['', ''])[1].upper() == 'CMS'
        and options.get('FLOW_ROUTING', ['', ''])[1].upper() == 'DYNWAVE'
        and options.get('LINK_OFFSETS', ['', 'DEPTH'])[1].upper() == 'DEPTH', 'BASIN_NETWORK_UNITS_INVALID')
    nodes = indexed(sections.get('JUNCTIONS', [])+sections.get('STORAGE', []))
    outfalls = indexed(sections.get('OUTFALLS', []))
    external_outfalls = set(outfalls)-{p['outfall'].upper() for p in source['ports']}
    graph = defaultdict(set)
    for section in ('CONDUITS', 'PUMPS', 'ORIFICES', 'WEIRS', 'OUTLETS'):
        for row in sections.get(section, []):
            graph[row['tokens'][1].upper()].add(row['tokens'][2].upper())
    used = {token.upper() for rows in sections.values() for row in rows for token in row['tokens']}
    occupied = set()
    port_cells = {i for p in source['ports'] for i in p['surfaceTriangles']}
    exposed = set(source['evaluationMetrics']['exposureTriangles'])
    added = {'OUTFALLS': [], 'ORIFICES': [], 'XSECTIONS': []}
    details = []
    for p in placements:
        require(isinstance(p, dict) and set(p) == {'id', 'facilityType', 'basis', 'evidence',
            'triangles', 'vertexElevations', 'material', 'drain'}, 'BASIN_PLACEMENT_INVALID')
        require(p['facilityType'] == 'RETENTION_BASIN' and p['basis'] == 'EXPLICIT_DESIGN_NOT_SITE_MEASURED'
                and isinstance(p['evidence'], str) and p['evidence'].strip(), 'BASIN_DESIGN_EVIDENCE_REQUIRED')
        cells = p['triangles']
        require(isinstance(cells, list) and cells and all(type(i) is int and 0 <= i < size for i in cells)
                and len(set(cells)) == len(cells), 'BASIN_REGION_INVALID')
        cells = set(cells)
        require(not cells.intersection(occupied | exposed | port_cells)
            and all(surface['rainfallOwner'][i] == 'SURFACE' for i in cells), 'BASIN_OWNERSHIP_CONFLICT')
        require(all(surface['initialDepthM'][i] == 0 for i in cells), 'BASIN_CONSTRUCTION_REQUIRES_DRY_SEED')
        seen, todo = set(), {min(cells)}
        while todo:
            cell = todo.pop(); seen.add(cell)
            todo.update((adjacency[cell] & cells)-seen)
        require(seen == cells, 'BASIN_REGION_DISCONNECTED')
        border = set()
        for edge, neighbors in edges.items():
            inside = cells.intersection(neighbors)
            if len(inside) == 1:
                require(len(neighbors) == 2, 'BASIN_DOMAIN_EDGE_NOT_ALLOWED')
                border.update(edge)
        vertices = {i for cell in cells for i in surface['triangles'][cell]}
        heights = p['vertexElevations']
        require(isinstance(heights, list) and len(heights) == len(vertices)
            and all(isinstance(row, dict) and set(row) == {'vertex', 'elevationM'}
                    and type(row['vertex']) is int for row in heights)
            and {row['vertex'] for row in heights} == vertices, 'BASIN_HEIGHT_COVERAGE_INVALID')
        for row in heights:
            vertex = row['vertex']
            height = number(row['elevationM'], -1000, 10000)
            old = original['elevationM'][vertex]
            require(old-100 <= height <= old and (vertex not in border or height == old),
                    'BASIN_BOUNDARY_OR_EXCAVATION_INVALID')
            surface['elevationM'][vertex] = height
        roughness, soil = material(surface['infiltration'], cells, p['material'], surface['rainfallOwner'])
        surface['infiltration'] = soil
        for cell in cells:
            surface['manningN'][cell] = roughness
        areas = [triangle_area(surface, i) for i in sorted(cells)]
        beds = [sum(surface['elevationM'][j] for j in surface['triangles'][i])/3 for i in sorted(cells)]
        excavation = math.fsum(triangle_area(surface, i)*sum(original['elevationM'][j]
            - surface['elevationM'][j] for j in surface['triangles'][i])/3 for i in cells)
        require(excavation > 0 and border, 'BASIN_EXCAVATION_REQUIRED')
        crest = min(surface['elevationM'][i] for i in border)
        capacity = math.fsum(a*max(0, crest-z) for a, z in zip(areas, beds))
        require(capacity > 0, 'BASIN_RETENTION_CAPACITY_REQUIRED')
        name = 'WLBS_'+identifier(p['id'])
        generated = {name.upper()+'_O', name.upper()+'_D'}
        require(not generated.intersection(used), 'BASIN_IDENTIFIER_COLLISION')
        used.update(generated)
        drain = p['drain']
        require(isinstance(drain, dict) and set(drain) == {'nodeId', 'triangles', 'crestM',
            'diameterM', 'dischargeCoefficient', 'evidence'} and drain['evidence'], 'BASIN_DRAIN_INVALID')
        target = identifier(drain['nodeId'], source=True).upper()
        require(target in nodes, 'BASIN_INTERNAL_NODE_REQUIRED')
        reachable, todo = set(), {target}
        while todo:
            node = todo.pop(); reachable.add(node); todo.update(graph[node]-reachable)
        require(reachable.intersection(external_outfalls), 'BASIN_DOWNSTREAM_CONNECTION_REQUIRED')
        region = drain['triangles']
        require(isinstance(region, list) and region and all(type(i) is int and i in cells for i in region)
                and len(set(region)) == len(region), 'BASIN_DRAIN_REGION_INVALID')
        height = number(drain['crestM'], -1000, 10000)
        diameter = number(drain['diameterM'], high=100, positive=True)
        coefficient = number(drain['dischargeCoefficient'], high=1, positive=True)
        try:
            invert, depth = float(nodes[target][1]), float(nodes[target][2])
        except (ValueError, IndexError):
            require(False, 'BASIN_SOURCE_NODE_INVALID')
        require(math.isfinite(invert) and math.isfinite(depth) and invert <= height < invert+depth
            and height <= crest and all(height >= max(surface['elevationM'][j]
            for j in surface['triangles'][i]) for i in region), 'BASIN_DRAIN_ELEVATION_INVALID')
        require(math.pi*diameter**2/4 <= math.fsum(triangle_area(surface, i) for i in region),
                'BASIN_DRAIN_AREA_INVALID')
        added['OUTFALLS'].append(f'{name}_O {height:.15g} FIXED {height:.15g} NO')
        added['ORIFICES'].append(f'{name}_D {nodes[target][0]} {name}_O BOTTOM {height-invert:.15g} {coefficient:.15g} NO 0')
        added['XSECTIONS'].append(f'{name}_D CIRCULAR {diameter:.15g} 0 0 0')
        source['ports'].append({'id': name, 'outfall': name+'_O', 'orifice': name+'_D', 'crestM': height,
                               'surfaceTriangles': region, 'evidence': drain['evidence']})
        details.append({'id': p['id'], 'portId': name, 'triangles': sorted(cells), 'areasM2': areas,
            'planAreaM2': math.fsum(areas), 'excavationM3': excavation, 'lowestBoundaryElevationM': crest,
            'storageToLowestBoundaryM3': capacity,
            'capacityMethod': 'DISCRETE_CENTROID_DEPTH_AT_LOWEST_BOUNDARY',
            'bedElevationM': beds, 'geometryVerifiedOnSite': False})
        occupied.update(cells)
    lines = text.splitlines(keepends=True)
    ending = '\r\n' if '\r\n' in text else '\n'
    for section, rows in added.items():
        append_section(lines, section, rows, ending)
    source['network']['inputText'] = ''.join(lines)
    surface['designTerrainProvenance'] = {'method': METHOD, 'sourceSurfaceSha256': digest(original),
                                         'sourceModelSha256': design['sourceModelSha256']}
    return source, {'schemaVersion': 1, 'method': METHOD, 'design': deepcopy(design),
        'sourceModelSha256': design['sourceModelSha256'], 'derivedModelSha256': digest(source),
        'compilerSha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'facilities': details,
        'rainfallOwnershipUnchanged': True, 'additionalNetworkStorageM3': 0,
        'rankingEligible': False, 'historicalReconstructionEligible': False,
        'limitations': ['설계 지형·재료·배수구이며 현장 형상/시공/단가 검증 아님',
            '지표 지형과 같은 수량 소유권; 부분 영역 물수지를 별도 계측한 결과 아님',
            '침투·증발은 기존 지표 모형의 근사와 관측 입력 한계 유지',
            '배수구는 국부 개구부이며 접속관 마찰/막힘·3차원 수직 흐름 제외',
            '격자 중심 수심 기반 저장량; 경계고 초과 물은 주변 지표와 같은 흐름으로 계산']}


def state_summary(metadata, state):
    result = []
    for row in metadata['facilities']:
        depths = [state['depthM'][i] for i in row['triangles']]
        require(all(type(v) in (int, float) and math.isfinite(v) and v >= 0 for v in depths),
                'BASIN_STATE_INVALID')
        result.append({'id': row['id'], 'storageM3': math.fsum(a*d for a, d in zip(row['areasM2'], depths)),
            'maximumDepthM': max(depths),
            'maximumStageAboveLowestBoundaryM': max(0., max((z+d-row['lowestBoundaryElevationM']
                for z,d in zip(row['bedElevationM'],depths) if d > 0), default=0.))})
    return {'timeSeconds': state['timeSeconds'], 'facilities': result}


def result_summary(metadata, surface, evaluation_origin=None):
    return {'design': metadata, 'initial': state_summary(metadata, surface['initial']),
        'evaluationInitial': state_summary(metadata, evaluation_origin) if evaluation_origin is not None else None,
        'final': state_summary(metadata, surface['final']),
        'includedInSurfaceStorageAndLosses': True, 'additionalStorageInCoupledBalanceM3': 0,
        'separateRegionFluxLedgerAvailable': False, 'rankingEligible': False}
