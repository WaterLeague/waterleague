"""원 관로 형상을 유지한 계산 구간 분할. 추가 절점은 실제 자산이 아님."""
from copy import deepcopy
import math
from pathlib import Path

from ..engine.connected_storage import append_section, indexed, number
from ..engine.flood_errors import require
from .published_network import digest, records


def _number(value):
    try:
        result = float(value)
    except (ValueError, TypeError):
        require(False, 'REFINEMENT_SOURCE_NUMBER_INVALID')
    require(math.isfinite(result), 'REFINEMENT_SOURCE_NUMBER_INVALID')
    return result


def refine(raw, request):
    text, sections = records(raw)
    require(isinstance(request, dict) and set(request) == {'schemaVersion', 'sourceNetworkSha256',
        'segmentsByConduit', 'minimumNumericalNodeAreaM2'} and type(request['schemaVersion']) is int
        and request['schemaVersion'] == 1 and request['sourceNetworkSha256'] == digest(raw),
        'REFINEMENT_SOURCE_BINDING_INVALID')
    counts = request['segmentsByConduit']
    require(isinstance(counts, dict) and 0 < len(counts) <= 128 and all(isinstance(k, str)
        and type(v) is int and 2 <= v <= 256 for k, v in counts.items())
        and len({k.upper() for k in counts}) == len(counts) and sum(counts.values()) <= 10000,
        'REFINEMENT_SEGMENTS_INVALID')
    minimum = number(request['minimumNumericalNodeAreaM2'], high=1000, positive=True)
    options = indexed(sections.get('OPTIONS', []))
    require(all(len(row) == 2 for row in options.values()), 'REFINEMENT_OPTION_FORMAT_INVALID')
    require(options.get('FLOW_UNITS', ['', ''])[1].upper() == 'CMS'
        and options.get('FLOW_ROUTING', ['', ''])[1].upper() == 'DYNWAVE'
        and options.get('LINK_OFFSETS', ['', 'DEPTH'])[1].upper() == 'DEPTH', 'REFINEMENT_UNITS_INVALID')
    conduits, shapes = [indexed(sections.get(k, [])) for k in ('CONDUITS', 'XSECTIONS')]
    junctions, outfalls = [indexed(sections.get(k, [])) for k in ('JUNCTIONS', 'OUTFALLS')]
    require(not set(junctions) & set(outfalls), 'REFINEMENT_NODE_DUPLICATE')
    nodes = junctions | outfalls
    counts = {key.upper(): value for key, value in counts.items()}
    require(set(counts) <= set(conduits) & set(shapes), 'REFINEMENT_CONDUIT_MISSING')
    for section in ('LOSSES', 'VERTICES'):
        require(not any(row['tokens'][0].upper() in counts for row in sections.get(section, [])),
                'REFINEMENT_SOURCE_FEATURE_UNSUPPORTED')
    require(not any(set(t.upper() for t in row['tokens']) & set(counts)
        for row in sections.get('CONTROLS', [])), 'REFINEMENT_CONTROL_UNSUPPORTED')
    used = {t.upper() for rows in sections.values() for row in rows for t in row['tokens']}
    new_nodes, details, replacement = [], [], {}
    end = '\r\n' if '\r\n' in text else '\n'
    for key, count in sorted(counts.items()):
        link, shape = conduits[key], shapes[key]
        require(7 <= len(link) <= 9 and len(shape) >= 3 and all(k.upper() in nodes for k in link[1:3]),
                'REFINEMENT_SOURCE_FORMAT_INVALID')
        require(shape[1].upper() in ('CIRCULAR', 'RECT_OPEN', 'STREET', 'TRAPEZOIDAL'),
                'REFINEMENT_SHAPE_UNSUPPORTED')
        require(all(_number(v) == 0 for v in link[5:]) and
            (len(shape) < 8 or _number(shape[7]) == 0), 'REFINEMENT_OFFSET_FLOW_OR_CULVERT_UNSUPPORTED')
        length, rough = _number(link[3]), _number(link[4])
        require(length > 0 and rough > 0 and length/count >= .01, 'REFINEMENT_LENGTH_INVALID')
        source_nodes = [nodes[k.upper()] for k in link[1:3]]
        require(all(len(row) >= 3 for row in source_nodes), 'REFINEMENT_NODE_FORMAT_INVALID')
        heights = [_number(row[1]) for row in source_nodes]
        depths, maximum_heads = [], []
        for row in source_nodes:
            if row[0].upper() in junctions:
                require(len(row) >= 4 and _number(row[3]) == 0,
                        'REFINEMENT_INITIAL_DEPTH_UNSUPPORTED')
                depths.append(_number(row[2]))
                surcharge = _number(row[4]) if len(row) > 4 else 0.
                require(surcharge >= 0, 'REFINEMENT_NODE_DEPTH_REQUIRED')
                maximum_heads.append(_number(row[1])+_number(row[2])+surcharge)
            else:
                require(row[2].upper() in ('FREE', 'NORMAL'), 'REFINEMENT_STAGE_BOUNDARY_UNSUPPORTED')
        require(depths and all(v > 0 for v in depths), 'REFINEMENT_NODE_DEPTH_REQUIRED')
        depth = max(depths)
        prefix = 'WLRF_'+digest(key.encode())[:12]
        seam_names = [f'{prefix}_N{i}' for i in range(1, count)]
        segment_names = [f'{prefix}_C{i}' for i in range(1, count)] + [link[0]]
        generated = {name.upper() for name in seam_names + segment_names[:-1]}
        require(not used.intersection(generated), 'REFINEMENT_ID_COLLISION')
        used.update(generated)
        chain = [link[1], *seam_names, link[2]]
        for i, name in enumerate(seam_names, 1):
            z = heights[0] + (heights[1]-heights[0])*i/count
            # 폐관 내부에 가상 맨홀 월류구를 만들지 않도록 원 끝 절점의 허용 수두를 유지한다.
            surcharge = max(0., max(maximum_heads)-z-depth) if shape[1].upper() == 'CIRCULAR' else 0.
            new_nodes.append(f'{name} {z:.15g} {depth:.15g} 0 {surcharge:.15g} 0')
        lengths = [length/count]*(count-1)
        lengths.append(length-math.fsum(lengths))
        rows, xs = [], []
        for i, name in enumerate(segment_names):
            rows.append(' '.join([name, chain[i], chain[i+1], f'{lengths[i]:.15g}', *link[4:]]))
            xs.append(' '.join([name, *shape[1:]]))
        replacement['CONDUITS', key] = rows
        replacement['XSECTIONS', key] = xs
        details.append({'originalConduitId': link[0], 'originalNodes': link[1:3],
            'originalLengthM': length, 'originalInvertM': heights, 'originalRoughness': rough,
            'originalCrossSection': shape[1:], 'segments': segment_names, 'segmentLengthsM': lengths,
            'numericalNodes': seam_names, 'numericalNodeMaximumDepthM': depth,
            'closedConduitMaximumHeadM': max(maximum_heads) if shape[1].upper() == 'CIRCULAR' else None,
            'numericalNodeClassification': 'COMPUTATIONAL_SEAM_NOT_MANHOLE_OR_STORAGE',
            'originalLinkOutputScope': 'DOWNSTREAM_SEGMENT_ONLY_AFTER_SUBDIVISION',
            'inletPlacement': 'ORIGINAL_DOWNSTREAM_END_ID_RETAINED'})
    lines = text.splitlines(keepends=True)
    for section in ('CONDUITS', 'XSECTIONS'):
        for row in sections[section]:
            value = replacement.get((section, row['tokens'][0].upper()))
            if value is not None:
                lines[row['line']-1] = end.join(value)+end
    previous = options.get('MIN_SURFAREA', ['', None])[1]
    for row in sections['OPTIONS']:
        if row['tokens'][0].upper() == 'MIN_SURFAREA':
            lines[row['line']-1] = f'MIN_SURFAREA {minimum:.15g}'+end
    if previous is None:
        append_section(lines, 'OPTIONS', [f'MIN_SURFAREA {minimum:.15g}'], end)
    append_section(lines, 'JUNCTIONS', new_nodes, end)
    derived = ''.join(lines).encode()
    require(len(derived) <= 2_000_000, 'REFINEMENT_INPUT_TOO_LARGE')
    return derived, {'schemaVersion': 1, 'method': 'EXPLICIT_CONDUIT_DISCRETIZATION_V1',
        'classification': 'NUMERICAL_DISCRETIZATION_NOT_NEW_PHYSICAL_ASSETS',
        'sourceNetworkSha256': digest(raw), 'derivedNetworkSha256': digest(derived),
        'compilerSha256': digest(Path(__file__).read_bytes()), 'request': deepcopy(request),
        'minimumNumericalNodeAreaM2': minimum, 'originalDeclaredMinimumAreaM2': previous,
        'conduits': details, 'rankingEligible': False,
        'limitations': ['원 길이·단면·조도·관저고 유지, 직선 수직 형상의 계산 구간 분할',
            '추가 절점은 실측 시설·추가 저류 면적이 아님; 최소 수치 면적의 영향 별도 확인 필요',
            '수치 절점 월류는 실제 지표 연결이 없으므로 승인 거부',
            '격자·시간 민감도와 물수지 통과는 현장 검증을 대체하지 않음']}


def assess_virtual_nodes(metadata, result):
    names = [node for link in metadata['conduits'] for node in link['numericalNodes']]
    final = result['final']['nodes']
    require(len(set(names)) == len(names) and all(name in final for name in names),
            'REFINEMENT_RESULT_NODE_MISSING')
    values = {name: final[name]['floodingM3'] for name in names}
    require(all(type(v) in (int, float) and math.isfinite(v) and v >= 0 for v in values.values()),
            'REFINEMENT_FLOODING_INVALID')
    total = math.fsum(values.values())
    return {'method': 'NO_UNMAPPED_COMPUTATIONAL_NODE_FLOODING_V1', 'floodingM3': total,
        'byNodeM3': values, 'status': 'PASSED' if total == 0 else 'FAILED'}
