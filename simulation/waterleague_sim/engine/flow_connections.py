"""공개 원형·모형 연결과 면적 배분의 근거. 유량·좌표·현장 대응을 추정하지 않는다."""
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re

from .flood_errors import require
from ..ingestion.published_network import records

VERSION = 'PUBLIC_SOURCE_FLOW_GRAPH_V1'


def encode(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False,
                       separators=(',', ':')) + '\n').encode('utf-8')


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def decimal(value):
    try:
        require(type(value) in (int, float, str, Decimal) and len(str(value)) <= 128,
                'FLOW_GRAPH_QUANTITY_INVALID')
        result = Decimal(str(value))
        require(result.is_finite() and 0 <= result <= 10**12
                and -18 <= result.as_tuple().exponent <= 12
                and len(result.as_tuple().digits) <= 24, 'FLOW_GRAPH_QUANTITY_INVALID')
        return result
    except (InvalidOperation, ValueError):
        require(False, 'FLOW_GRAPH_QUANTITY_INVALID')


def amount(value):
    if decimal(value) == 0:
        return '0'
    result = format(decimal(value), 'f')
    return result.rstrip('0').rstrip('.') if '.' in result else result


def scaled_area(value):
    # 큰 면적에 더한 미소 초과량이 Decimal 컨텍스트 반올림에 숨지 않게 한다.
    numerator, denominator = decimal(value).as_integer_ratio()
    return numerator * 10**18 // denominator


def validate(value):
    require(isinstance(value, dict) and value.get('version') == VERSION
            and value.get('mode') in ('NATIVE_DIRECT_SURFACE', 'PUBLISHED_NETWORK_DESIGN'),
            'FLOW_GRAPH_SCHEMA_INVALID')
    require(isinstance(value.get('nodes'), list) and 1 <= len(value['nodes']) <= 4096
            and isinstance(value.get('edges'), list) and len(value['edges']) <= 8192
            and isinstance(value.get('areaBudgets'), list) and len(value['areaBudgets']) <= 4096,
            'FLOW_GRAPH_SIZE_INVALID')
    ids, edge_ids, allocations, budgets, pools = set(), set(), set(), set(), set()
    source_totals = {}
    for node in value['nodes']:
        key = node.get('id') if isinstance(node, dict) else None
        require(isinstance(key, str) and 0 < len(key) <= 256 and key not in ids,
                'FLOW_GRAPH_NODE_DUPLICATED_OR_INVALID')
        ids.add(key)
    for edge in value['edges']:
        require(isinstance(edge, dict) and isinstance(edge.get('id'), str)
                and 0 < len(edge['id']) <= 256 and edge['id'] not in edge_ids
                and isinstance(edge.get('from'), str) and edge['from'] in ids
                and isinstance(edge.get('to'), str) and edge['to'] in ids,
                'FLOW_GRAPH_EDGE_DUPLICATED_OR_MISSING')
        edge_ids.add(edge['id'])
    for budget in value['areaBudgets']:
        key = budget.get('id') if isinstance(budget, dict) else None
        require(isinstance(key, str) and 0 < len(key) <= 256 and key not in budgets
                and isinstance(budget.get('sourceNodeId'), str) and budget['sourceNodeId'] in ids
                and budget.get('unit') == 'm2'
                and type(budget.get('completePartition')) is bool
                and budget.get('surfaceClass') in ('TOTAL', 'IMPERVIOUS', 'PERVIOUS')
                and isinstance(budget.get('allocations'), list) and len(budget['allocations']) <= 4096,
                'FLOW_GRAPH_BUDGET_INVALID')
        budgets.add(key)
        pool = (budget['sourceNodeId'], budget['surfaceClass'])
        require(pool not in pools, 'FLOW_GRAPH_SOURCE_POOL_REUSED')
        pools.add(pool)
        available, used = scaled_area(budget.get('availableM2')), 0
        source_totals[budget['sourceNodeId']] = source_totals.get(budget['sourceNodeId'], 0) + available
        for row in budget['allocations']:
            require(isinstance(row, dict) and isinstance(row.get('id'), str)
                    and 0 < len(row['id']) <= 256 and row['id'] not in allocations
                    and isinstance(row.get('targetNodeId'), str) and row['targetNodeId'] in ids,
                    'FLOW_GRAPH_ALLOCATION_REUSED_OR_MISSING')
            allocations.add(row['id'])
            used += scaled_area(row.get('areaM2'))
        require(used <= available, 'FLOW_GRAPH_CAPTURE_AREA_EXCEEDED')
        if budget.get('completePartition'):
            require(used == available, 'FLOW_GRAPH_PARTITION_AREA_MISMATCH')
    for node in value['nodes']:
        if node['id'] in source_totals:
            require(source_totals[node['id']] == scaled_area(node.get('areaM2')),
                    'FLOW_GRAPH_SOURCE_AREA_MISMATCH')
            classes = {kind for source, kind in pools if source == node['id']}
            require(classes in ({'TOTAL'}, {'IMPERVIOUS', 'PERVIOUS'}), 'FLOW_GRAPH_SOURCE_POOL_REUSED')
    sources = value.get('sourceHashes')
    require(isinstance(sources, dict) and 0 < len(sources) <= 64
            and all(isinstance(k, str) and isinstance(v, str) and re.fullmatch('[a-f0-9]{64}', v)
                    for k, v in sources.items()), 'FLOW_GRAPH_SOURCE_HASH_INVALID')
    require(isinstance(value.get('inputBindings'), list) and len(value['inputBindings']) <= 16384
            and isinstance(value.get('evaluationPoints'), list) and len(value['evaluationPoints']) <= 4096,
            'FLOW_GRAPH_SIZE_INVALID')
    for binding in value['inputBindings']:
        require(isinstance(binding, dict) and isinstance(binding.get('nodeId'), str)
                and binding['nodeId'] in ids and isinstance(binding.get('source'), str)
                and binding['source'] in sources and isinstance(binding.get('pointer'), str)
                and 0 < len(binding['pointer']) <= 256, 'FLOW_GRAPH_INPUT_BINDING_INVALID')
    require(all(isinstance(point, dict) and isinstance(point.get('nodeId'), str)
                and point['nodeId'] in ids for point in value['evaluationPoints']),
            'FLOW_GRAPH_EVALUATION_POINT_MISSING')
    for row in value['nodes'] + value['edges']:
        if 'source' in row:
            require(isinstance(row['source'], str) and row['source'] in sources,
                    'FLOW_GRAPH_SOURCE_REFERENCE_INVALID')
    try:
        raw = encode(value)
    except (ValueError, TypeError, OverflowError):
        require(False, 'FLOW_GRAPH_SCHEMA_INVALID')
    require(len(raw) <= 4 * 1024**2, 'FLOW_GRAPH_SIZE_INVALID')
    return value


def stamp(value):
    value['implementationSha256'] = digest(Path(__file__).read_bytes())
    validate(value)
    return {'sha256': digest(encode(value)), **value}


def direct_surface(model, placement, result, input_files):
    cell, = model['cells']
    geometry = model['geometrySource']
    total, installed = decimal(cell['areaM2']), decimal(placement['areaM2'])
    require(installed <= decimal(cell['maxAreaM2']) <= total, 'FLOW_GRAPH_CAPTURE_AREA_EXCEEDED')
    candidate, facility, outlet, remainder = [prefix + cell['id'] for prefix in
                                             ('candidate:', 'facility:', 'surface-outlet:', 'remainder:')]
    original = 'object:' + cell['sourceObjectId']
    sources = {**input_files, 'objectCatalog': geometry['objectsSha256'],
               'siteCatalog': geometry['playCatalogSha256'],
               'candidateGeometry': geometry['geometrySha256']}
    return stamp({
        'version': VERSION, 'mode': 'NATIVE_DIRECT_SURFACE', 'sourceHashes': sources,
        'spatialStatus': {'horizontalCrs': 'EPSG:5186', 'verticalDatum': 'UNCONFIRMED',
                          'drainageNetworkLink': 'UNCONNECTED', 'surfaceGridLink': 'UNCONNECTED'},
        'nodes': [
            {'id': original, 'kind': 'SPATIAL_OBJECT', 'sourceObjectId': cell['sourceObjectId'],
             'source': 'objectCatalog'},
            {'id': candidate, 'kind': 'INSTALLATION_CANDIDATE', 'candidateId': cell['id'],
             'districtId': cell['districtId'], 'areaM2': amount(total),
             'geometrySha256': cell['geometrySha256'], 'source': 'siteCatalog'},
            {'id': facility, 'kind': 'FACILITY', 'facilityType': placement['facilityType'],
             'areaM2': amount(installed), 'source': 'placement.json'},
            {'id': remainder, 'kind': 'MODEL_SURFACE_REMAINDER', 'areaM2': amount(total-installed),
             'geometry': None, 'source': 'model.json'},
            {'id': outlet, 'kind': 'COMPUTATIONAL_SURFACE_OUTLET', 'drainageNodeId': None,
             'source': 'model.json'},
        ],
        'edges': [
            {'id': 'source-candidate', 'from': original, 'to': candidate, 'kind': 'SOURCE_DERIVATION'},
            {'id': 'facility-direct-rain', 'from': candidate, 'to': facility, 'kind': 'DIRECT_RAIN_AREA'},
            {'id': 'remaining-direct-rain', 'from': candidate, 'to': remainder, 'kind': 'DIRECT_RAIN_AREA'},
            {'id': 'facility-outlet', 'from': facility, 'to': outlet, 'kind': 'SURFACE_AND_LID_DRAINAGE'},
            {'id': 'remainder-outlet', 'from': remainder, 'to': outlet, 'kind': 'BYPASS_SURFACE_RUNOFF'},
        ],
        'areaBudgets': [{'id': candidate, 'sourceNodeId': candidate, 'availableM2': amount(total),
                         'unit': 'm2', 'surfaceClass': 'TOTAL', 'completePartition': True,
                         'allocations': [{'id': 'facility-direct-rain', 'targetNodeId': facility,
                                          'areaM2': amount(installed)},
                                         {'id': 'remaining-direct-rain', 'targetNodeId': remainder,
                                          'areaM2': amount(total-installed)}]}],
        'inputBindings': [
            {'nodeId': candidate, 'role': role, 'source': 'model.json', 'pointer': pointer}
            for role, pointer in (('RAINFALL', '/rainfall'), ('SOIL_AND_COVER_REFERENCE', '/cells/0/physicalInputs'),
                                  ('INITIAL_STATE_PARAMETERS', '/hydrology'),
                                  ('INITIAL_STATE_POLICY', '/initialization'))
            if role != 'INITIAL_STATE_POLICY' or 'initialization' in model
        ],
        'evaluationPoints': [{'nodeId': outlet, 'kind': 'COMPUTED_SURFACE_OUTLET',
                              'start': result['baseline']['initial']['at'],
                              'end': result['baseline']['final']['at'],
                              'method': result['runoffComparison']['method']}],
        'unresolved': ['EXTERNAL_CATCHMENT_AND_DRAINAGE_NETWORK_NOT_CONNECTED',
                       'MODEL_AREA_REMAINDER_HAS_NO_MEASURED_SUBPOLYGON'],
    })


def unique_surfaces(placements):
    require(isinstance(placements, list) and 1 <= len(placements) <= 50, 'FLOW_GRAPH_SURFACE_ID_INVALID')
    keys = set()
    for row in placements:
        require(isinstance(row, dict) and isinstance(row.get('districtId'), str)
                and isinstance(row.get('cellId'), str), 'FLOW_GRAPH_SURFACE_ID_INVALID')
        key = (row['districtId'], row['cellId'])
        require(key not in keys, 'FLOW_GRAPH_SURFACE_REUSED')
        keys.add(key)


def published_network(original, baseline, strategy, design, transformation, source_hashes, cases):
    sources = dict(source_hashes)
    for name, raw in (('original.inp', original), ('baseline-input.inp', baseline),
                      ('strategy-input.inp', strategy)):
        require(sources.get(name) == digest(raw), 'FLOW_GRAPH_SOURCE_HASH_MISMATCH')
    require(sources.get('design.json') == digest(encode(design)), 'FLOW_GRAPH_SOURCE_HASH_MISMATCH')
    original_sections, sections = records(original)[1], records(strategy)[1]
    nodes, edges, bindings, budgets, points = [], [], [], [], []

    def key(prefix, name):
        return prefix + ':' + name.upper()

    def reference(source, section, row):
        return {'source': source, 'section': section, 'line': row['line'],
                'rowSha256': digest(row['text'].encode('utf-8'))}

    def bind(node, role, section, rows, source='strategy-input.inp'):
        for row in rows:
            bindings.append({'nodeId': node, 'role': role, 'source': source,
                             'pointer': section + '@' + str(row['line']),
                             'rowSha256': digest(row['text'].encode('utf-8'))})

    for section in ('JUNCTIONS', 'STORAGE', 'OUTFALLS', 'DIVIDERS'):
        for row in sections.get(section, []):
            node = key('node', row['tokens'][0])
            nodes.append({'id': node, 'kind': section, 'modelId': row['tokens'][0],
                          **reference('strategy-input.inp', section, row)})
            bind(node, 'NODE_INITIAL_STATE_AND_BOUNDARY', section, [row])
            bind(node, 'EXTERNAL_INFLOW', 'INFLOWS', [r for r in sections.get('INFLOWS', [])
                                                     if r['tokens'][0].upper() == row['tokens'][0].upper()])
    for section in ('CONDUITS', 'PUMPS', 'ORIFICES', 'WEIRS', 'OUTLETS'):
        for row in sections.get(section, []):
            t = row['tokens']
            require(len(t) >= 3, 'FLOW_GRAPH_NETWORK_RECORD_INVALID')
            edges.append({'id': key('link', t[0]), 'from': key('node', t[1]), 'to': key('node', t[2]),
                          'kind': 'DECLARED_NETWORK_LINK', 'linkType': section,
                          'directionBasis': 'INP_ORIENTATION_DYNAMIC_FLOW_MAY_REVERSE',
                          **reference('strategy-input.inp', section, row)})
    for row in sections.get('SUBCATCHMENTS', []):
        t = row['tokens']
        require(len(t) >= 8, 'FLOW_GRAPH_NETWORK_RECORD_INVALID')
        node = key('catchment', t[0])
        nodes.append({'id': node, 'kind': 'MODEL_CATCHMENT', 'modelId': t[0],
                      **reference('strategy-input.inp', 'SUBCATCHMENTS', row)})
        edges.append({'id': key('runoff', t[0]), 'from': node,
                      'to': key('catchment' if any(r['tokens'][0].upper() == t[2].upper()
                               for r in sections['SUBCATCHMENTS']) else 'node', t[2]),
                      'kind': 'SWMM_CATCHMENT_OUTLET',
                      **reference('strategy-input.inp', 'SUBCATCHMENTS', row)})
        for role, section in (('SOIL_MODEL_PARAMETERS', 'INFILTRATION'),
                              ('COVER_MODEL_PARAMETERS', 'SUBAREAS')):
            bind(node, role, section, [r for r in sections.get(section, [])
                                      if r['tokens'][0].upper() == t[0].upper()])
        gauges = [r for r in sections.get('RAINGAGES', []) if r['tokens'][0].upper() == t[1].upper()]
        bind(node, 'RAINFALL_GAUGE_MODEL_PARAMETER', 'RAINGAGES', gauges)
        series = {r['tokens'][5].upper() for r in gauges
                  if len(r['tokens']) > 5 and r['tokens'][4].upper() == 'TIMESERIES'}
        bind(node, 'RAINFALL_SERIES_OBSERVATIONAL_LINEAGE_UNCONFIRMED', 'TIMESERIES',
             [r for r in sections.get('TIMESERIES', []) if r['tokens'][0].upper() in series])
        bind(node, 'INITIAL_STATE_AND_CLOCK', 'OPTIONS', sections.get('OPTIONS', []))
        bind(node, 'EVAPORATION_MODEL_PARAMETER', 'EVAPORATION', sections.get('EVAPORATION', []))

    facilities = {p['id'].upper(): p for p in transformation.get('facilities', [])}
    for p in design['placements']:
        detail = facilities.get(p['id'].upper())
        require(detail is not None, 'FLOW_GRAPH_FACILITY_MISSING')
        node, host = key('facility', p['id']), key('catchment', detail['subcatchmentId'])
        usage = [r for r in sections.get('LID_USAGE', [])
                 if r['tokens'][1].upper() == detail['swmmId'].upper()
                 and r['tokens'][0].upper() == detail['subcatchmentId'].upper()]
        require(len(usage) == 1, 'FLOW_GRAPH_FACILITY_USAGE_MISSING')
        nodes.append({'id': node, 'kind': 'LID_FACILITY', 'facilityType': p['facilityType'],
                      'sourceCatchmentId': p['subcatchmentId'], 'executionCatchmentId': detail['subcatchmentId'],
                      **reference('strategy-input.inp', 'LID_USAGE', usage[0])})
        covered = p['facilityType'] == 'RAINWATER_CISTERN'
        if covered:
            nodes[-1]['coverRainfallStatus'] = 'EXCLUDED_WITHOUT_MODELED_BYPASS'
        for kind in (('ALLOCATED_IMPERVIOUS_RUNOFF',) if covered else ('DIRECT_RAIN_AREA', 'ALLOCATED_IMPERVIOUS_RUNOFF')):
            edges.append({'id': kind + ':' + p['id'].upper(), 'from': host, 'to': node, 'kind': kind})
        edges.append({'id': key('lid-outlet', p['id']), 'from': node,
                      'to': key('node', detail['outletNodeId']), 'kind': 'SURFACE_AND_LID_DRAINAGE'})
        bind(node, 'FACILITY_INITIAL_SATURATION_AND_CAPTURE', 'LID_USAGE', usage)
        bind(node, 'FACILITY_DESIGN_PARAMETERS', 'LID_CONTROLS', [r for r in sections.get('LID_CONTROLS', [])
                                                                 if r['tokens'][0].upper() == detail['swmmId'].upper()])

    cistern = transformation.get('networkCistern')
    for row in original_sections.get('SUBCATCHMENTS', []):
        t = row['tokens']
        require(len(t) >= 8 and decimal(t[4]) <= 100, 'FLOW_GRAPH_NETWORK_RECORD_INVALID')
        original_id = key('source-catchment', t[0])
        area = decimal(t[3]) * 10000
        nodes.append({'id': original_id, 'kind': 'SOURCE_MODEL_CATCHMENT', 'areaM2': amount(area),
                      'areaBasis': 'DECLARED_MODEL_HECTARES_NOT_MEASURED_POLYGON',
                      **reference('original.inp', 'SUBCATCHMENTS', row)})
        impervious = area * decimal(t[4]) / 100
        pools = {'impervious': [impervious, []], 'pervious': [area-impervious, []]}

        def allocate(pool, target, quantity, role, suffix):
            pools[pool][1].append({'id': original_id + ':' + suffix, 'targetNodeId': target,
                                   'areaM2': amount(quantity), 'role': role})

        for p in design['placements']:
            if p['subcatchmentId'].upper() != t[0].upper():
                continue
            facility = key('facility', p['id'])
            removed, footprint, captured = (decimal(p[k]) for k in
                                            ('replacedImperviousM2', 'areaM2', 'treatedImperviousM2'))
            require(removed <= footprint, 'FLOW_GRAPH_CAPTURE_AREA_EXCEEDED')
            direct_role = 'UNMODELED_COVER_RAIN' if p['facilityType'] == 'RAINWATER_CISTERN' else 'FACILITY_DIRECT_RAIN'
            allocate('impervious', facility, removed, direct_role, p['id'] + ':footprint-imp')
            allocate('pervious', facility, footprint-removed, direct_role, p['id'] + ':footprint-perv')
            allocate('impervious', facility, captured, 'ROUTED_RUNOFF_NOT_ADDITIONAL_RAIN', p['id'] + ':capture')
        bypass = key('catchment', t[0])
        if cistern and cistern['catchmentPartition']['hostId'].upper() == t[0].upper():
            partition = cistern['catchmentPartition']
            target = key('node', cistern['facilities'][0]['nodeId'])
            capture, cover = decimal(partition['captureAreaM2']), decimal(partition['coverAreaM2'])
            allocate('impervious', target, capture, 'CISTERN_ROUTED_RUNOFF_NOT_DIRECT_RAIN', 'cistern-capture')
            bypass = key('catchment', partition.get('imperviousBypassId', partition['hostId']))
            cover_target = key('catchment', partition['coverId']) if 'coverId' in partition else bypass
            allocate('impervious', cover_target, cover, 'CISTERN_COVER_RAIN_BYPASS', 'cistern-cover')
            edges.append({'id': original_id + ':cistern-partition', 'from': original_id,
                          'to': key('catchment', partition['captureId']), 'kind': 'EXPLICIT_MODEL_PARTITION'})
            for role, target_id in (('cover', partition.get('coverId')),
                                    ('impervious-bypass', partition.get('imperviousBypassId'))):
                if target_id is not None and target_id.upper() != t[0].upper():
                    edges.append({'id': original_id + ':' + role, 'from': original_id,
                                  'to': key('catchment', target_id), 'kind': 'EXPLICIT_MODEL_PARTITION'})
        edges.append({'id': original_id + ':source', 'from': original_id,
                      'to': key('catchment', t[0]), 'kind': 'SOURCE_MODEL_DERIVATION'})
        for pool, (available, allocations) in pools.items():
            used = sum((decimal(p['areaM2']) for p in allocations), Decimal(0))
            require(used <= available, 'FLOW_GRAPH_CAPTURE_AREA_EXCEEDED')
            allocate(pool, bypass if pool == 'impervious' else key('catchment', t[0]),
                     available-used, 'UNALLOCATED_BYPASS_RAIN', pool + ':bypass')
            budgets.append({'id': original_id + ':' + pool, 'sourceNodeId': original_id,
                            'availableM2': amount(available), 'unit': 'm2', 'surfaceClass': pool.upper(),
                            'completePartition': True,
                            'allocations': allocations})

    for case in cases:
        metrics = case.get('evaluationMetrics')
        if metrics:
            for outfall in metrics['specification']['networkOutfalls']:
                points.append({'nodeId': key('node', outfall), 'case': case['id'],
                               'kind': 'COMPUTED_MODEL_OUTFALL', 'method': metrics['method'],
                               'specificationSha256': metrics['specificationSha256'],
                               'startMilliseconds': metrics['specification']['startMilliseconds'],
                               'endMilliseconds': metrics['specification']['endMilliseconds']})
    return stamp({'version': VERSION, 'mode': 'PUBLISHED_NETWORK_DESIGN', 'sourceHashes': sources,
                  'spatialStatus': {'horizontalCrs': 'UNCONFIRMED', 'verticalDatum': 'UNCONFIRMED',
                                    'nativeMapLink': 'UNCONNECTED', 'surfaceGridLink': 'UNCONNECTED'},
                  'nodes': nodes, 'edges': edges, 'areaBudgets': budgets, 'inputBindings': bindings,
                  'evaluationPoints': points,
                  'unresolved': ['MODEL_CATCHMENTS_HAVE_NO_VERIFIED_NATIVE_POLYGON_LINK',
                                 'RAINFALL_STATION_TIME_ZONE_AND_OBSERVATIONAL_LINEAGE_UNCONFIRMED',
                                 'PUBLISHED_MODEL_PARAMETERS_NOT_FIELD_MEASUREMENTS']})


def archive(value, directory):
    value = dict(value)
    expected = value.pop('sha256', None)
    validate(value)
    raw = encode(value)
    require(digest(raw) == expected, 'FLOW_GRAPH_HASH_MISMATCH')
    directory = Path(directory)
    (directory / 'flow-graph.json').write_bytes(raw)
    (directory / 'flow_connections.py').write_bytes(Path(__file__).read_bytes())
