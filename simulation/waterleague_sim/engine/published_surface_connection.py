"""공개 관망·원 지형을 보존하는 명시적 지표 교환 시나리오."""
from copy import deepcopy
import hashlib
import math
from pathlib import Path

from .flood_errors import require
from ..ingestion.published_network import records, inspect_input
from ..terrain.grid import digest
from ..terrain.rainfall_coverage import validate as validate_rainfall

METHOD = 'PUBLISHED_SURFACE_CONNECTION_EXPLORATION_V1'
DATUM_POLICY = 'SOURCE_BOUND_COMMON_DATUM_ASSUMPTION_V1'
FACILITY_OBSERVER = 'PUBLISHED_COUPLED_FACILITY_OBSERVER_V1'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _number(value, minimum, maximum):
    return type(value) in (int, float) and math.isfinite(value) and minimum <= value <= maximum


def _append(lines, section, additions):
    marker = next((i for i, line in enumerate(lines) if line.strip().upper() == '['+section+']'), None)
    if marker is None:
        lines.extend(['', '['+section+']', *additions])
    else:
        lines[marker+1:marker+1] = additions


def compile_connection(request):
    import numpy as np
    from pyproj import CRS
    from shapely.geometry import Polygon, Point
    from shapely import STRtree
    require(isinstance(request, dict) and set(request) == {'schemaVersion', 'method', 'sourceNetworkText',
        'sourceSurface', 'sourceLocation', 'sourceCoverage', 'parameters', 'evidence'}
        and type(request['schemaVersion']) is int and request['schemaVersion'] == 1
        and request['method'] == METHOD and isinstance(request['evidence'], str) and request['evidence'].strip(),
        'PUBLIC_CONNECTION_REQUEST_INVALID')
    original = request['sourceNetworkText'].encode()
    source, location, params = request['sourceSurface'], request['sourceLocation'], request['parameters']
    require(isinstance(source, dict) and source.get('schemaVersion') == 2
            and isinstance(location, dict) and location.get('sourceOriginalSha256') == sha(original)
            and location.get('rankingEligible') is False and location.get('sourceCrsVerified') is False,
            'PUBLIC_CONNECTION_SOURCE_INVALID')
    required = {'openingDiameterM', 'dischargeCoefficient', 'surchargeHeadM', 'surfaceOffsetM',
                'boundaryType', 'durationSeconds', 'maximumExchangeMilliseconds', 'frameIntervalMilliseconds',
                'networkNumericalProfile'}
    require(isinstance(params, dict) and set(params) == required
            and _number(params['openingDiameterM'], .01, 5)
            and _number(params['dischargeCoefficient'], .01, 1)
            and _number(params['surchargeHeadM'], 1, 1000)
            and _number(params['surfaceOffsetM'], -10, 10)
            and params['boundaryType'] in ('REFLECTIVE', 'TRANSMISSIVE')
            and type(params['durationSeconds']) is int and 1 <= params['durationSeconds'] <= 86400
            and type(params['maximumExchangeMilliseconds']) is int
            and 1 <= params['maximumExchangeMilliseconds'] <= 60000
            and type(params['frameIntervalMilliseconds']) is int
            and 1 <= params['frameIntervalMilliseconds'] <= params['durationSeconds']*1000,
            'PUBLIC_CONNECTION_PARAMETERS_INVALID')
    provenance = source.get('terrainProvenance', {})
    require(provenance.get('absoluteVerticalReferenceVerified') is False
            and CRS.from_wkt(provenance['coordinateWkt']) == CRS(location['horizontalCrs'])
            and isinstance(provenance.get('originProjected'), list)
            and len(provenance['originProjected']) == 2,
            'PUBLIC_CONNECTION_TERRAIN_REFERENCE_INVALID')
    text, sections = records(original)
    network = inspect_input(original)
    require(network['options']['FLOW_UNITS'] == 'CMS' and network['options']['FLOW_ROUTING'] == 'DYNWAVE'
            and network['options'].get('LINK_OFFSETS', 'DEPTH') == 'DEPTH'
            and network['options']['ALLOW_PONDING'] == 'NO'
            and not any(sections.get(s) for s in ('STORAGE', 'ORIFICES', 'LID_USAGE', 'CONTROLS', 'FILES')),
            'PUBLIC_CONNECTION_NETWORK_UNSUPPORTED')
    from ..ingestion.network_variant import derive_compiled
    derive_compiled(original, params['networkNumericalProfile'])
    validate_rainfall({'network': {'inputText': text, 'coordinateSystem': source['coordinateSystem']},
        'surface': source, 'networkRainfallCoverage': request['sourceCoverage']})
    datum = {'method': DATUM_POLICY, 'networkOriginalSha256': sha(original),
        'sourceSurfaceSha256': digest(source), 'sourceLocationSha256': digest(location),
        'surfaceOffsetM': params['surfaceOffsetM'], 'networkDatumVerified': False,
        'surfaceDatumVerified': False, 'rankingEligible': False,
        'evidence': request['evidence']}
    shared = 'ASSUMED_COMMON_DATUM:'+digest(datum)
    surface = deepcopy(source)
    surface['elevationM'] = [z+params['surfaceOffsetM'] for z in source['elevationM']]
    surface.update(verticalDatum=shared, evidence='PUBLIC_INPUT_UNVERIFIED_DATUM_COUPLING_EXPLORATION',
                   rankingEligible=False)
    surface['boundaryConditions'] = {tag: {'type': params['boundaryType']} for tag in source['boundaryConditions']}
    surface['terrainProvenance']['couplingHeightAssumption'] = deepcopy(datum)
    points = np.asarray(surface['verticesM'])
    triangles = np.asarray(surface['triangles'])
    polygons = [Polygon(points[t]) for t in triangles]
    tree = STRtree(polygons)
    nodes = {row['id']: row for row in network['nodes']}
    require(set(nodes) == {row['id'] for row in location['nodes']}, 'PUBLIC_CONNECTION_NODES_MISMATCH')
    junctions = {row['tokens'][0]: row for row in sections['JUNCTIONS']}
    lines, occupied, ports, details = text.splitlines(), set(), [], []
    outfalls, orifices, xsections = [], [], []
    names = {row['tokens'][0].upper() for rows in sections.values() for row in rows}
    origin = provenance['originProjected']
    for node in location['nodes']:
        n = nodes[node['id']]
        if n['kind'] != 'JUNCTION':
            continue
        row = junctions[node['id']]
        fields = row['tokens']
        require(len(fields) == 6 and float(fields[4]) == float(fields[5]) == 0,
                'PUBLIC_CONNECTION_JUNCTION_UNSUPPORTED')
        xy = [node['coordinate'][i]-origin[i] for i in (0, 1)]
        cells = tree.query(Point(xy), predicate='covered_by').tolist()
        require(cells, 'PUBLIC_CONNECTION_NODE_OUTSIDE_MESH')
        cell = min(cells)
        require(cell not in occupied, 'PUBLIC_CONNECTION_PORT_COLLISION')
        occupied.add(cell)
        bed = float(np.mean(np.asarray(surface['elevationM'])[triangles[cell]]))
        invert, depth = float(fields[1]), float(fields[2])
        rim = invert+depth
        crest = max(rim, bed)
        require(crest < rim+params['surchargeHeadM'], 'PUBLIC_CONNECTION_HEAD_LIMIT_TOO_LOW')
        identifier, outlet, orifice = 'PORT_'+node['id'], 'WL_SURF_'+node['id'], 'WL_PORT_'+node['id']
        require(outlet.upper() not in names and orifice.upper() not in names,
                'PUBLIC_CONNECTION_IDENTIFIER_CONFLICT')
        names.update((outlet.upper(), orifice.upper()))
        lines[row['line']-1] = ' '.join(fields[:4]+[str(params['surchargeHeadM']), fields[5]])
        outfalls.append(f'{outlet} {crest:.15g} FIXED {crest:.15g} NO')
        orifices.append(f'{orifice} {node["id"]} {outlet} BOTTOM {crest-invert:.15g} '
                        f'{params["dischargeCoefficient"]} NO 0')
        xsections.append(f'{orifice} CIRCULAR {params["openingDiameterM"]} 0 0 0')
        ports.append({'id': identifier, 'outfall': outlet, 'orifice': orifice, 'crestM': crest,
            'surfaceTriangles': [cell], 'evidence': 'PUBLIC_NODE_POSITION_ASSUMED_EQUIVALENT_OPENING'})
        details.append({'nodeId': node['id'], 'sourceCoordinate': node['coordinate'], 'localCoordinateM': xy,
            'surfaceTriangle': cell, 'regionAreaM2': polygons[cell].area, 'sourceInvertM': invert,
            'sourceRimM': rim, 'surfaceCentroidBedM': bed, 'surfaceMinusRimM': bed-rim,
            'exchangeCrestM': crest, 'gridCrestRaiseM': crest-rim, 'surchargeHeadM': params['surchargeHeadM'],
            'openingDiameterM': params['openingDiameterM'], 'openingAreaM2': math.pi*params['openingDiameterM']**2/4,
            'dischargeCoefficient': params['dischargeCoefficient']})
    for section, additions in (('OUTFALLS', outfalls), ('ORIFICES', orifices), ('XSECTIONS', xsections)):
        _append(lines, section, additions)
    prepared = '\n'.join(lines)+'\n'
    gages = sections.get('RAINGAGES', [])
    require(len(gages) == 1 and gages[0]['tokens'][1:5] == ['INTENSITY', '1:00', '1.0', 'TIMESERIES'],
            'PUBLIC_CONNECTION_RAINFALL_UNSUPPORTED')
    name = gages[0]['tokens'][5]
    events, times = [], []
    for row in sections['TIMESERIES']:
        f = row['tokens']
        if f[0] != name:
            continue
        require(len(f) == 3 and _number(float(f[1]), 0, 48) and _number(float(f[2]), 0, 1000),
                'PUBLIC_CONNECTION_RAINFALL_UNSUPPORTED')
        seconds = float(f[1])*3600
        require(seconds.is_integer() and (not times or seconds > times[-1]),
                'PUBLIC_CONNECTION_RAINFALL_TIMING_INVALID')
        times.append(seconds)
        if seconds < params['durationSeconds']:
            events.append({'timeMilliseconds': int(seconds)*1000,
                'ratesMmH': [float(f[2]) if owner == 'SURFACE' else 0. for owner in surface['rainfallOwner']],
                'evidence': 'PUBLISHED_HOURLY_RESEARCH_RAIN_STATION_TIMEZONE_UNVERIFIED'})
    require(events and events[0]['timeMilliseconds'] == 0 and times[-1]+3600 >= params['durationSeconds'],
            'PUBLIC_CONNECTION_RAINFALL_COVERAGE_INCOMPLETE')
    summary = {'schemaVersion': 1, 'method': METHOD, 'originalNetworkSha256': sha(original),
        'sourceSurfaceSha256': digest(source), 'sourceLocationSha256': digest(location),
        'preparedNetworkSha256': sha(prepared.encode()), 'parameters': deepcopy(params), 'ports': details,
        'verticalReferenceAssumption': datum, 'nativeFloodingPolicy': 'REJECT_ANY_UNMAPPED_FLOODING',
        'sourceForcingPreserved': True, 'rankingEligible': False,
        'compilerSha256': sha(Path(__file__).read_bytes()),
        'limitations': ['원 절점에 가정한 등가 원형 개구부이며 실제 빗물받이·뚜껑 개방 관측 아님',
            '지형·관망 높이 기준과 개구부 크기·경계의 시나리오 민감도 필요',
            '격자 평균 바닥보다 낮은 원 문턱은 교환 문턱만 높인 격자 근사',
            '원 강우 관측소·시간대 미확인과 추정 외부 유입 보존; 관측 사건 복원 아님']}
    return {'schemaVersion': 1, 'evidence': 'PUBLIC_SOURCE_CONNECTION_EXPLORATION_NOT_SITE_VALIDATED',
        'durationSeconds': params['durationSeconds'], 'maximumExchangeMilliseconds': params['maximumExchangeMilliseconds'],
        'frameIntervalMilliseconds': params['frameIntervalMilliseconds'], 'surface': surface,
        'network': {'inputText': prepared, 'coordinateSystem': surface['coordinateSystem'], 'verticalDatum': shared},
        'networkRainfallCoverage': deepcopy(request['sourceCoverage']), 'surfaceRainfall': events, 'ports': ports,
        'networkNumericalProfile': deepcopy(params['networkNumericalProfile']),
        'evaluationMetrics': {'schemaVersion': 1, 'policyVersion': METHOD,
            'evidence': 'PUBLIC_TERRAIN_WINDOW_NOT_OBSERVED_DAMAGE', 'startMilliseconds': 0,
            'endMilliseconds': params['durationSeconds']*1000,
            'networkOutfalls': [n['id'] for n in network['nodes'] if n['kind'] == 'OUTFALL'],
            'exposureTriangles': list(range(len(triangles))), 'wetDepthThresholdM': .01},
        'publishedSurfaceConnection': {'request': deepcopy(request), 'summary': summary}}


def validate(model):
    binding = model.get('publishedSurfaceConnection')
    require(isinstance(binding, dict) and set(binding) == {'request', 'summary'}, 'PUBLIC_CONNECTION_BINDING_REQUIRED')
    expected = compile_connection(binding['request'])
    require(set(model) <= set(expected) | {'dryExchangePolicy', 'connectedFacilityDesign', 'networkObserverPolicy'}
            and all(model.get(key) == value for key, value in expected.items()), 'PUBLIC_CONNECTION_BINDING_MISMATCH')
    require('networkObserverPolicy' not in model or model['networkObserverPolicy'] == FACILITY_OBSERVER,
            'PUBLIC_CONNECTION_OBSERVER_INVALID')
    if 'connectedFacilityDesign' in model:
        from .connected_facilities import compile_design
        # 시설은 원 집수구역 안에서만 배분하며 지형·교환구·원 강우 결속을 바꾸지 않는다.
        compile_design(expected['network']['inputText'].encode(), model['connectedFacilityDesign'])
    return expected['publishedSurfaceConnection']['summary']
