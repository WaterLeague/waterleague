"""원 집수 다각형과 계산 격자의 강우 면적 분할·선언 면적 보존."""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import re

from ..engine.flood_errors import require

METHOD = 'GEOMETRIC_RAINFALL_PARTITION_V1'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    allow_nan=False).encode()).hexdigest()


def source_hash():
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def surface_fractions(surface):
    owners = surface.get('rainfallOwner')
    require(isinstance(owners, list) and 0 < len(owners) <= 200_000
            and all(v in ('SURFACE', 'NETWORK') for v in owners), 'RAIN_PARTITION_OWNERS_INVALID')
    partition = surface.get('rainfallPartition')
    if partition is None:
        return [1. if v == 'SURFACE' else 0. for v in owners]
    require(isinstance(partition, dict) and set(partition) ==
            {'method', 'coverageSha256', 'surfaceFractions'} and partition['method'] == METHOD
            and isinstance(partition['coverageSha256'], str)
            and re.fullmatch(r'[a-f0-9]{64}', partition['coverageSha256']), 'RAIN_PARTITION_INVALID')
    fractions = partition['surfaceFractions']
    require(isinstance(fractions, list) and len(fractions) == len(owners)
            and all(type(v) in (int, float) and math.isfinite(v)
                    and ((owner == 'NETWORK' and v == 0) or (owner == 'SURFACE' and 0 < v <= 1))
                    for owner, v in zip(owners, fractions)), 'RAIN_PARTITION_FRACTIONS_INVALID')
    return fractions[:]


def declared_areas(network):
    units, rows, section = None, {}, ''
    for line in network['inputText'].splitlines():
        fields = line.split(';', 1)[0].split()
        if fields and fields[0].startswith('['):
            section = fields[0].upper()
        elif fields and section == '[OPTIONS]' and fields[0].upper() == 'FLOW_UNITS':
            require(len(fields) == 2 and units is None, 'RAIN_PARTITION_UNITS_INVALID')
            units = fields[1].upper()
        elif fields and section == '[SUBCATCHMENTS]':
            require(len(fields) >= 4 and fields[0] not in rows, 'RAIN_PARTITION_CATCHMENTS_INVALID')
            try:
                value = float(fields[3])
            except ValueError:
                require(False, 'RAIN_PARTITION_CATCHMENTS_INVALID')
            require(math.isfinite(value) and value > 0, 'RAIN_PARTITION_CATCHMENTS_INVALID')
            rows[fields[0]] = value
    require(units in ('CMS', 'LPS', 'MLD', 'CFS', 'GPM', 'MGD'), 'RAIN_PARTITION_UNITS_INVALID')
    factor = 10000. if units in ('CMS', 'LPS', 'MLD') else 4046.8564224
    return {name: value*factor for name, value in sorted(rows.items())}


def compile_coverage(surface, network, specification):
    import numpy as np
    import shapely
    from shapely.geometry import Polygon, shape
    spec = deepcopy(specification)
    require(isinstance(spec, dict) and type(spec.get('schemaVersion')) is int
            and spec.get('schemaVersion') == 1 and spec.get('method') == METHOD
            and spec.get('coordinateSystem') == surface.get('coordinateSystem')
            and spec.get('coordinateSystem') == network.get('coordinateSystem')
            and isinstance(spec.get('evidence'), str) and spec['evidence'].strip()
            and isinstance(spec.get('source'), dict) and spec['source'].get('reference')
            and isinstance(spec['source'].get('sha256'), str)
            and re.fullmatch(r'[a-f0-9]{64}', spec['source']['sha256']), 'RAIN_PARTITION_SPECIFICATION_INVALID')
    points, triangles = np.asarray(surface['verticesM']), np.asarray(surface['triangles'])
    require(points.ndim == 2 and points.shape[1] == 2 and 3 <= len(points) <= 500_000
            and np.issubdtype(points.dtype, np.number) and np.all(np.isfinite(points))
            and triangles.ndim == 2 and triangles.shape[1] == 3 and 0 < len(triangles) <= 200_000
            and np.issubdtype(triangles.dtype, np.integer) and np.all(triangles >= 0)
            and np.all(triangles < len(points)), 'RAIN_PARTITION_MESH_INVALID')
    mesh = [Polygon(points[t]) for t in triangles]
    a = points[triangles[:, 1]]-points[triangles[:, 0]]
    b = points[triangles[:, 2]]-points[triangles[:, 0]]
    require(all(p.is_valid and p.area > 0 for p in mesh) and shapely.coverage_is_valid(mesh)
            and np.all(a[:, 0]*b[:, 1]-a[:, 1]*b[:, 0] > 0)
            and len({tuple(sorted(t)) for t in surface['triangles']}) == len(mesh), 'RAIN_PARTITION_MESH_INVALID')
    domain, tree = shapely.union_all(mesh), shapely.STRtree(mesh)
    declared = declared_areas(network)
    rows = spec.get('catchments')
    require(isinstance(rows, list) and 0 < len(rows) <= 10000
            and all(isinstance(row, dict) and isinstance(row.get('id'), str) for row in rows)
            and len({r['id'] for r in rows}) == len(rows)
            and {r['id'] for r in rows} == set(declared), 'RAIN_PARTITION_CATCHMENTS_INVALID')
    geometries = []
    for row in rows:
        try:
            g = shape(row['geometry'])
        except (KeyError, ValueError, TypeError, shapely.GEOSException):
            require(False, 'RAIN_PARTITION_GEOMETRY_INVALID')
        require(g.geom_type in ('Polygon', 'MultiPolygon') and not g.has_z and not g.has_m
                and not g.is_empty and g.is_valid and math.isfinite(g.area) and g.area > 0
                and np.all(np.isfinite(shapely.get_coordinates(g))), 'RAIN_PARTITION_GEOMETRY_INVALID')
        require(domain.covers(g), 'RAIN_PARTITION_OUTSIDE_MESH')
        geometries.append(g)
    catchment_tree = shapely.STRtree(geometries)
    for i, g in enumerate(geometries):
        require(all(j <= i or g.intersection(geometries[j]).area == 0
                    for j in catchment_tree.query(g, predicate='intersects')), 'RAIN_PARTITION_GEOMETRY_OVERLAP')
    parts, result_rows, entries = [[] for _ in mesh], [], 0
    for row, g in sorted(zip(rows, geometries), key=lambda pair: pair[0]['id']):
        cells = []
        for index in sorted(tree.query(g, predicate='intersects').tolist()):
            area = mesh[index].intersection(g).area
            if area > 0:
                cells.append([index, area])
                parts[index].append(area)
        entries += len(cells)
        require(entries <= 2_000_000, 'RAIN_PARTITION_ENTRY_LIMIT')
        total = math.fsum(a for _, a in cells)
        require(math.isclose(total, g.area, rel_tol=1e-10, abs_tol=1e-8), 'RAIN_PARTITION_GEOMETRY_LOSS')
        result_rows.append({'id': row['id'], 'declaredAreaM2': declared[row['id']],
            'geometryAreaM2': g.area, 'intersections': cells, 'intersectionAreaM2': total,
            'intersectionResidualM2': total-g.area, 'declaredMinusGeometryM2': declared[row['id']]-g.area})
    fractions, roundoff = [], []
    for cell, areas in zip(mesh, parts):
        covered = math.fsum(areas)
        require(covered <= cell.area + max(1e-8, cell.area*1e-10), 'RAIN_PARTITION_AREA_OVERLAP')
        # 교차 연산의 반올림만 한정하고 보정 면적을 원장에 남긴다.
        remaining = max(0., cell.area-covered)
        fractions.append(remaining/cell.area)
        roundoff.append(cell.area-remaining-covered)
    total = math.fsum(p.area for p in mesh)
    direct = math.fsum(p.area*f for p, f in zip(mesh, fractions))
    geometry = math.fsum(r['geometryAreaM2'] for r in result_rows)
    declared_total = math.fsum(declared.values())
    result = {'schemaVersion': 1, 'method': METHOD, 'specification': spec,
        'meshSha256': digest({'verticesM': surface['verticesM'], 'triangles': surface['triangles']}),
        'declaredAreasSha256': digest(declared), 'catchments': result_rows,
        'surfaceFractions': fractions, 'allocationRoundoffByTriangleM2': roundoff,
        'totals': {'meshAreaM2': total, 'surfaceRainfallAreaM2': direct,
            'networkGeometryAreaM2': geometry, 'networkDeclaredAreaM2': declared_total,
            'declaredMinusGeometryM2': declared_total-geometry,
            'combinedForcingAreaM2': direct+declared_total,
            'combinedMinusMeshM2': direct+declared_total-total,
            'geometryClosureResidualM2': direct+geometry-total,
            'allocationRoundoffM2': math.fsum(roundoff)},
        'implementation': {'adapterSha256': source_hash(), 'shapely': shapely.__version__,
                           'geos': shapely.geos_version_string},
        'areaPolicy': 'PRESERVE_SWMM_DECLARED_AREA_REPORT_GEOMETRIC_DIFFERENCE',
        'limitations': ['원 지도 경계와 선언 집수면적은 서로 다른 입력이며 자동 보정하지 않음',
                       '경계 격자는 공통 수심을 갖는 면적 평균; 격자 이하 흐름 경계 복원 아님']}
    return result


def bind(surface, network, specification):
    coverage = compile_coverage(surface, network, specification)
    fractions = coverage['surfaceFractions']
    prepared = deepcopy(surface)
    prepared['rainfallOwner'] = ['SURFACE' if f > 0 else 'NETWORK' for f in fractions]
    prepared['rainfallPartition'] = {'method': METHOD, 'coverageSha256': digest(coverage),
                                   'surfaceFractions': fractions[:]}
    return prepared, coverage


def validate(model):
    surface = model['surface']
    surface_fractions(surface)
    coverage = model.get('networkRainfallCoverage')
    require(isinstance(coverage, dict) and not model.get('networkRainfallTriangles'), 'RAIN_PARTITION_CONFLICT')
    expected_surface, expected = bind(surface, model['network'], coverage.get('specification'))
    require(coverage == expected and surface['rainfallOwner'] == expected_surface['rainfallOwner']
            and surface.get('rainfallPartition') == expected_surface['rainfallPartition'],
            'RAIN_PARTITION_BINDING_MISMATCH')
    return coverage


def has_network_rainfall(model):
    return bool(model.get('networkRainfallCoverage') or model.get('networkRainfallTriangles'))


def rainfall_difference(coverage, depths_by_catchment):
    require(set(depths_by_catchment) == {r['id'] for r in coverage['catchments']}
            and all(type(d) in (int, float) and math.isfinite(d) and d >= 0
                    for d in depths_by_catchment.values()), 'RAIN_PARTITION_DEPTH_INVALID')
    return {'method': METHOD, 'coverageSha256': digest(coverage),
        'declaredMinusGeometryRainfallM3': math.fsum(r['declaredMinusGeometryM2']*
            depths_by_catchment[r['id']]/1000 for r in coverage['catchments']),
        'geometryNetworkRainfallM3': math.fsum(r['geometryAreaM2']*
            depths_by_catchment[r['id']]/1000 for r in coverage['catchments'])}


def network_rainfall_difference(coverage, rainfall):
    depths = {row['stationId']: row['depthMm'] for row in rainfall['stations']}
    return rainfall_difference(coverage, {name: depths[sid] for name, sid in
                                         rainfall['stationByCatchment'].items()})
