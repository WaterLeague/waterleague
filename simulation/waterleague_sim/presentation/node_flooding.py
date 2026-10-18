"""관망 내부 단계의 절점별 월류를 원본 도형과 결속한 표시 자료."""
import json
import math

from waterleague_sim.engine.flood_errors import require
from waterleague_sim.engine.swmm import ROOT
from waterleague_sim.ingestion.published_network import digest

LAYOUT = ROOT/'backend/src/main/resources/watersheds/seocho-layout-v1.json'
LAYOUT_HASH = 'fa3e4d833650df5c40d933bd0b289dd029a54e0beb73fad9b9d3ef239cb0236d'
METHOD = 'NATIVE_ROUTING_STEP_FLOODING_TRAPEZOIDAL_INTEGRAL'


def load_layout(original_hash):
    raw = LAYOUT.read_bytes()
    require(digest(raw) == LAYOUT_HASH, 'WATERSHED_LAYOUT_CHANGED')
    value = json.loads(raw)
    require(value['sourceOriginalSha256'] == original_hash, 'WATERSHED_LAYOUT_SOURCE_MISMATCH')
    return raw, {'sha256': LAYOUT_HASH, 'layout': value}


def summarize(initial, final, layout, delivery_nodes=()):
    def finite(value):
        return type(value) in (int, float) and math.isfinite(value) and value >= 0
    source = {n['id']: n for n in layout['nodes']}
    nodes = final['nodes']
    require(initial['totals']['timeSeconds'] == 0 and initial['totals']['floodingM3'] == 0
            and set(initial['nodes']) == set(nodes) and set(source) <= set(nodes)
            and all(n['floodingM3'] == 0 for n in initial['nodes'].values()),
            'WATERSHED_NODE_FLOODING_WINDOW_INVALID')
    rows = []
    for name, node in nodes.items():
        require(finite(node['floodingM3']) and type(node['type']) is int
                and node['type'] in (0, 1, 2), 'WATERSHED_NODE_FLOODING_INVALID')
        if name in source:
            require(node['type'] == (1 if source[name]['kind'] == 'OUTFALL' else 0),
                    'WATERSHED_NODE_LAYOUT_MISMATCH')
        else:
            # 추가 저류·토출 절점은 실제 위치를 만들어 원본 관망도에 그리지 않는다.
            require(node['type'] == 2 or node['type'] == 0 and name in delivery_nodes,
                    'WATERSHED_NODE_LOCATION_MISSING')
        rows.append({'id': name, 'kind': ('JUNCTION', 'OUTFALL', 'STORAGE')[node['type']],
                     'mapped': name in source, 'floodingM3': node['floodingM3']})
    total = final['totals']['floodingM3']
    end = final['totals']['timeSeconds']
    summed = math.fsum(n['floodingM3'] for n in rows)
    require(finite(total) and finite(end) and end > 0 and
            math.isclose(total, summed, rel_tol=1e-9, abs_tol=1e-8),
            'WATERSHED_NODE_FLOODING_TOTAL_MISMATCH')
    return {'schemaVersion': 1, 'method': METHOD, 'startSeconds': 0, 'endSeconds': end,
            'layoutSha256': LAYOUT_HASH, 'nodes': rows, 'totalFloodingM3': total,
            'sumNodeFloodingM3': summed, 'balanceDifferenceM3': summed-total}
