"""배수구와 원 관망 사이의 명시적 접속관·접속부 월류."""
from copy import deepcopy
from decimal import Decimal
import math

from .connected_storage import number
from .flood_errors import require


def compile_outlet(pipe, name, suffix, port, receiver, receiver_invert, receiver_depth):
    require(isinstance(pipe, dict) and set(pipe) == {
        'lengthM', 'diameterM', 'roughness', 'upstreamInvertM',
        'upstreamMaxDepthM', 'downstreamInvertM'}, 'CISTERN_OUTLET_PIPE_INVALID')
    length = number(pipe['lengthM'], .001, 10000)
    diameter = number(pipe['diameterM'], .001, 100)
    roughness = number(pipe['roughness'], .001, 1)
    upstream = number(pipe['upstreamInvertM'], -1000, 10000)
    depth = number(pipe['upstreamMaxDepthM'], .001, 100)
    downstream = number(pipe['downstreamInvertM'], -1000, 10000)
    d = lambda value: Decimal(str(value))
    require(d(depth) >= d(diameter)
        and d(upstream) <= d(port['crestM'])
        and d(port['crestM']) + d(port['diameterM']) <= d(upstream) + d(depth)
        and d(receiver_invert) <= d(downstream)
        and d(downstream) + d(diameter) <= d(receiver_invert) + d(receiver_depth)
        and 0 <= d(upstream) - d(downstream) <= d(length),
        'CISTERN_OUTLET_ELEVATION_INVALID')
    node, link = name + '_' + suffix + 'J', name + '_' + suffix + 'C'
    return {
        'JUNCTIONS': [f'{node} {upstream:.15g} {depth:.15g} 0 0 0'],
        'CONDUITS': [f'{link} {node} {receiver} {length:.15g} {roughness:.15g} '
                     f'0 {downstream-receiver_invert:.15g} 0 0'],
        'XSECTIONS': [f'{link} CIRCULAR {diameter:.15g} 0 0 0 1'],
    }, {'nodeId': node, 'linkId': link, 'receiverNodeId': receiver, **deepcopy(pipe),
        'method': 'EXPLICIT_CIRCULAR_CONDUIT_DYNWAVE_V1',
        'basis': 'EXPLICIT_DESIGN_NOT_MEASURED_OUTLET_PIPE',
        'initialDepthM': 0, 'surchargeDepthM': 0, 'pondedAreaM2': 0,
        'minorLossCoefficients': [0, 0, 0], 'flapGate': False}


def outlet_ledgers(metadata, origin, final):
    result = {}
    for kind, pipe in metadata.get('outletPipes', {}).items():
        name = pipe['nodeId']
        require(name in origin['nodes'] and name in final['nodes'], 'CISTERN_OUTLET_NODE_MISSING')
        before, after = origin['nodes'][name], final['nodes'][name]
        require(before['type'] == after['type'] == 0, 'CISTERN_OUTLET_NODE_TYPE_INVALID')
        flooding = after['floodingM3'] - before['floodingM3']
        require(all(math.isfinite(v) and v >= -1e-9
            for v in (flooding, before['depthM'], after['depthM'])),
            'CISTERN_OUTLET_COUNTER_INVALID')
        # 관내 저류·유량은 관망 수지에 포함되며 이용조 저류·유출에 재합산하지 않는다.
        result[kind] = {'nodeId': name, 'linkId': pipe['linkId'],
            'receiverNodeId': pipe['receiverNodeId'],
            'initialDepthM': before['depthM'], 'finalDepthM': after['depthM'],
            'floodingM3': flooding, 'numericalStatus': 'PASSED' if flooding <= 1e-9 else 'FAILED',
            'scope': 'UNCONNECTED_OUTLET_FLOODING_ALREADY_INCLUDED_IN_NETWORK'}
    return result
