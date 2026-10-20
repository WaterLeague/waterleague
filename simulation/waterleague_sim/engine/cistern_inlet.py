"""명시적 집수 연결관과 미연결 입구 월류 검사."""
from copy import deepcopy
from decimal import Decimal
import math
from .connected_storage import number
from .flood_errors import require


def compile_inlet(pipe, name, invert, depth):
    require(isinstance(pipe, dict) and set(pipe) == {
        'lengthM', 'diameterM', 'roughness', 'upstreamInvertM',
        'upstreamMaxDepthM', 'downstreamInvertM'}, 'CISTERN_INLET_PIPE_INVALID')
    length = number(pipe['lengthM'], .001, 10000)
    diameter = number(pipe['diameterM'], .001, 100)
    roughness = number(pipe['roughness'], .001, 1)
    upstream = number(pipe['upstreamInvertM'], -1000, 10000)
    upstream_depth = number(pipe['upstreamMaxDepthM'], .001, 100)
    downstream = number(pipe['downstreamInvertM'], -1000, 10000)
    d = lambda value: Decimal(str(value))
    # 서버의 십진 높이 경계가 이진 소수 뺄셈 오차로 거부되지 않게 한다.
    require(d(upstream_depth) >= d(diameter) and d(invert) <= d(downstream)
        and d(downstream) + d(diameter) <= d(invert) + d(depth)
        and 0 <= d(upstream) - d(downstream) <= d(length), 'CISTERN_INLET_ELEVATION_INVALID')
    node, link = name + '_U', name + '_I'
    return {
        'JUNCTIONS': [f'{node} {upstream:.15g} {upstream_depth:.15g} 0 0 0'],
        'CONDUITS': [f'{link} {node} {name} {length:.15g} {roughness:.15g} '
                     f'0 {downstream-invert:.15g} 0 0'],
        'XSECTIONS': [f'{link} CIRCULAR {diameter:.15g} 0 0 0 1'],
    }, {'nodeId': node, 'linkId': link, 'tankNodeId': name, **deepcopy(pipe),
        'method': 'EXPLICIT_CIRCULAR_CONDUIT_DYNWAVE_V1',
        'basis': 'EXPLICIT_DESIGN_NOT_MEASURED_GUTTER',
        'initialDepthM': 0, 'surchargeDepthM': 0, 'pondedAreaM2': 0,
        'minorLossCoefficients': [0, 0, 0], 'flapGate': False}


def inlet_ledger(metadata, origin, final):
    inlet = metadata.get('inletPipe')
    if inlet is None:
        return None
    name = inlet['nodeId']
    require(name in origin['nodes'] and name in final['nodes'], 'CISTERN_INLET_NODE_MISSING')
    before, after = origin['nodes'][name], final['nodes'][name]
    require(before['type'] == after['type'] == 0, 'CISTERN_INLET_NODE_TYPE_INVALID')
    flooding = after['floodingM3'] - before['floodingM3']
    values = [flooding, before['depthM'], after['depthM']]
    require(all(math.isfinite(v) and v >= -1e-9 for v in values),
            'CISTERN_INLET_COUNTER_INVALID')
    # 접속관의 저장·이동량은 전체 관망 수지에 이미 포함되므로 이용조 수지에 다시 더하지 않는다.
    return {'nodeId': name, 'linkId': inlet['linkId'],
        'initialDepthM': before['depthM'], 'finalDepthM': after['depthM'],
        'floodingM3': flooding, 'numericalStatus': 'PASSED' if flooding <= 1e-9 else 'FAILED',
        'scope': 'UNCONNECTED_INLET_FLOODING_ALREADY_INCLUDED_IN_NETWORK'}
