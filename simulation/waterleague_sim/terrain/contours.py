"""공개 등고선·표고점의 출처를 보존하는 무외삽 선형 지형."""
from decimal import Decimal, InvalidOperation
from copy import deepcopy
import math
import re

import shapely
from shapely.geometry import MultiPoint, Point, Polygon, mapping, shape
from shapely.strtree import STRtree
from pyproj import CRS

from waterleague_sim.engine.flood_errors import FloodModelError, require
from waterleague_sim.terrain.grid import digest, finite, surface_from_grid

METHOD = 'NGII_CONTOUR_SPOT_CONFORMING_TIN_V1'
FIELDS = {'CONTOUR_LINE': ('등고수치', ('LineString', 'MultiLineString')),
          'ELEVATION_POINT': ('수치', ('Point',))}


def _height(value):
    require(isinstance(value, str) and len(value) <= 40, 'CONTOUR_HEIGHT_INVALID')
    try:
        number = Decimal(value)
        require(number.is_finite(), 'CONTOUR_HEIGHT_INVALID')
        result = float(number)
    except (InvalidOperation, ValueError, OverflowError):
        raise FloodModelError('CONTOUR_HEIGHT_INVALID') from None
    require(finite(result), 'CONTOUR_HEIGHT_INVALID')
    return result


def controls(records):
    require(isinstance(records, list) and 1 <= len(records) <= 20_000,
            'CONTOUR_RECORDS_INVALID')
    points, identifiers = {}, set()
    for index, row in enumerate(records):
        require(isinstance(row, dict) and row.get('role') in FIELDS
                and row.get('scaleDenominator') == 1000
                and isinstance(row.get('id'), str) and row['id'] and row['id'] not in identifiers,
                'CONTOUR_RECORD_INVALID')
        identifiers.add(row['id'])
        for key in ('sourceShapeSha256', 'sourceDbfSha256', 'spatialCatalogSha256'):
            require(isinstance(row.get(key), str) and re.fullmatch('[0-9a-f]{64}', row[key]),
                    'CONTOUR_SOURCE_HASH_REQUIRED')
        field, kinds = FIELDS[row['role']]
        require(isinstance(row.get('attributes'), dict), 'CONTOUR_ATTRIBUTES_REQUIRED')
        z = _height(row['attributes'].get(field))
        try:
            geometry = shape(row['geometry'])
        except (TypeError, KeyError, ValueError, AttributeError):
            raise FloodModelError('CONTOUR_GEOMETRY_INVALID') from None
        require(not geometry.is_empty and geometry.is_valid and geometry.geom_type in kinds
                and shapely.get_coordinate_dimension(geometry) == 2,
                'CONTOUR_GEOMETRY_INVALID')
        coordinates = shapely.get_coordinates(geometry).tolist()
        require(all(len(xy) == 2 and all(map(finite, xy)) for xy in coordinates),
                'CONTOUR_COORDINATES_INVALID')
        for xy in coordinates:
            key = tuple(xy)
            if key in points:
                require(points[key]['heightM'] == z, 'CONTOUR_HEIGHT_CONFLICT')
                points[key]['recordIndexes'].add(index)
            else:
                points[key] = {'heightM': z, 'recordIndexes': {index}}
        require(len(points) <= 200_000, 'CONTOUR_VERTEX_LIMIT')
    require(len({r['spatialCatalogSha256'] for r in records}) == 1,
            'CONTOUR_CATALOG_MISMATCH')
    return [{'xy': list(xy), 'heightM': row['heightM'],
             'recordIndexes': sorted(row['recordIndexes'])} for xy, row in sorted(points.items())]


class ContourTin:
    def __init__(self, records):
        require(isinstance(records, list) and all(isinstance(r, dict) and isinstance(r.get('id'), str)
                for r in records), 'CONTOUR_RECORDS_INVALID')
        self.records = deepcopy(sorted(records, key=lambda r: r['id']))
        original_points = controls(self.records)
        self.original_point_count = len(original_points)
        require(len(original_points) >= 3, 'CONTOUR_POINTS_INSUFFICIENT')
        points = {tuple(p['xy']): dict(p, derivedFromSegments=[]) for p in original_points}
        segments = []
        for record_index, record in enumerate(self.records):
            if record['role'] != 'CONTOUR_LINE':
                continue
            g = shape(record['geometry'])
            for part, line in enumerate(g.geoms if g.geom_type == 'MultiLineString' else [g]):
                xy = list(line.coords)
                for i, (a, b) in enumerate(zip(xy, xy[1:])):
                    if a != b:
                        segments.append({'a': a, 'b': b, 'recordIndex': record_index, 'part': part,
                                         'segment': i, 'startFraction': 0., 'endFraction': 1.})
        coordinates = sorted(points)
        cloud = MultiPoint(coordinates)
        self.hull = cloud.convex_hull
        require(self.hull.geom_type == 'Polygon' and self.hull.area > 0,
                'CONTOUR_POINTS_COLLINEAR')
        self.refinement = []
        for iteration in range(17):
            coordinates = sorted(points)
            lookup = {xy: i for i, xy in enumerate(coordinates)}
            raw = shapely.delaunay_triangles(MultiPoint(coordinates), tolerance=0)
            triples, edges = [], set()
            for polygon in raw.geoms:
                xy = list(polygon.exterior.coords)[:-1]
                require(len(xy) == 3 and all(p in lookup for p in xy), 'CONTOUR_TIN_VERTEX_CHANGED')
                triples.append(tuple(sorted(lookup[p] for p in xy)))
                edges.update(tuple(sorted((xy[i], xy[(i+1) % 3]))) for i in range(3))
            require(len(triples) == len(set(triples))
                    and {i for t in triples for i in t} == set(lookup.values()), 'CONTOUR_TIN_VERTEX_LOST')
            missing = [s for s in segments if tuple(sorted((s['a'], s['b']))) not in edges]
            self.refinement.append({'iteration': iteration, 'vertices': len(points),
                                    'missingContourEdges': len(missing)})
            if not missing:
                break
            require(iteration < 16, 'CONTOUR_CONFORMING_REFINEMENT_LIMIT')
            updated = []
            for segment in segments:
                a, b = segment['a'], segment['b']
                if tuple(sorted((a, b))) in edges:
                    updated.append(segment)
                    continue
                # 누락된 등고선 변만 이분하고 파생점의 원 선분·분할 비율을 보존한다.
                mid = tuple((x+y)/2 for x, y in zip(a, b, strict=True))
                require(mid not in (a, b), 'CONTOUR_REFINEMENT_COLLAPSED')
                fraction = (segment['startFraction']+segment['endFraction'])/2
                z, record_index = points[a]['heightM'], segment['recordIndex']
                require(z == points[b]['heightM'], 'CONTOUR_SEGMENT_HEIGHT_MISMATCH')
                if mid not in points:
                    points[mid] = {'xy': list(mid), 'heightM': z, 'recordIndexes': [], 'derivedFromSegments': []}
                require(points[mid]['heightM'] == z, 'CONTOUR_HEIGHT_CONFLICT')
                point = points[mid]
                point['recordIndexes'] = sorted(set(point['recordIndexes']) | {record_index})
                point['derivedFromSegments'].append({k: segment[k] for k in ('recordIndex', 'part', 'segment')}
                                                    | {'fraction': fraction})
                updated.extend([segment | {'b': mid, 'endFraction': fraction},
                                segment | {'a': mid, 'startFraction': fraction}])
            require(len(points) <= 200_000, 'CONTOUR_VERTEX_LIMIT')
            segments = updated
        self.points = [points[xy] for xy in coordinates]
        self.segments = [{k: v for k, v in s.items() if k not in ('a', 'b')}
                         | {'vertices': [lookup[s['a']], lookup[s['b']]]} for s in segments]
        self.triangles = sorted(triples)
        self.polygons = [Polygon([coordinates[i] for i in t]) for t in self.triangles]
        require(shapely.coverage_is_valid(self.polygons)
                and shapely.coverage_union_all(self.polygons).equals(self.hull),
                'CONTOUR_TIN_COVERAGE_INVALID')
        self.index = STRtree(self.polygons)
        self.identity = digest(self.describe())

    def sample(self, xy):
        require(isinstance(xy, (list, tuple)) and len(xy) == 2 and all(map(finite, xy)),
                'CONTOUR_SAMPLE_INVALID')
        point = Point(xy)
        indexes = self.index.query(point, predicate='covered_by')
        # 경계에 여유를 더해 볼록껍질 밖을 안쪽으로 바꾸지 않는다.
        if len(indexes) == 0:
            require(not self.hull.covers(point), 'CONTOUR_TIN_INTERNAL_GAP')
            return None
        index = int(min(indexes))
        points = [self.points[i] for i in self.triangles[index]]
        (ax, ay), (bx, by), (cx, cy) = [p['xy'] for p in points]
        x, y = xy
        determinant = (by-cy)*(ax-cx)+(cx-bx)*(ay-cy)
        require(determinant != 0, 'CONTOUR_TIN_DEGENERATE')
        a = ((by-cy)*(x-cx)+(cx-bx)*(y-cy))/determinant
        b = ((cy-ay)*(x-cx)+(ax-cx)*(y-cy))/determinant
        weights = [a, b, 1-a-b]
        z = math.fsum(w*p['heightM'] for w, p in zip(weights, points, strict=True))
        require(finite(z) and min(weights) >= -1e-10 and max(weights) <= 1+1e-10,
                'CONTOUR_TIN_WEIGHTS_INVALID')
        return {'heightM': z, 'triangleIndex': index, 'weights': weights}

    def describe(self):
        return {'method': METHOD, 'recordsSha256': digest(self.records), 'points': self.points,
                'triangles': self.triangles, 'hull': mapping(self.hull), 'snapToleranceM': 0,
                'extrapolationAllowed': False, 'contourEdgesConstrained': True,
                'originalControlPointCount': self.original_point_count,
                'refinement': self.refinement, 'contourSegments': self.segments,
                'versions': {'shapely': shapely.__version__, 'geos': shapely.geos_version_string}}

    def grid(self, bounds, spacing, source_files, vertical_reference):
        require(isinstance(bounds, list) and len(bounds) == 4 and all(map(finite, bounds))
                and bounds[0] < bounds[2] and bounds[1] < bounds[3]
                and finite(spacing) and spacing > 0, 'CONTOUR_GRID_BOUNDS_INVALID')
        nx, ny = (bounds[2]-bounds[0])/spacing, (bounds[3]-bounds[1])/spacing
        require(nx.is_integer() and ny.is_integer() and 2*nx*ny <= 200_000,
                'CONTOUR_GRID_DIMENSIONS_INVALID')
        width, height = int(nx)+1, int(ny)+1
        values, supports = [], []
        for row in range(height):
            for column in range(width):
                sample = self.sample([bounds[0]+column*spacing, bounds[3]-row*spacing])
                require(sample is not None, 'CONTOUR_GRID_OUTSIDE_SUPPORT')
                values.append(sample['heightM'])
                supports.append(sample['triangleIndex'])
        return {'schemaVersion': 1, 'width': width, 'height': height,
                'coordinateWkt': CRS(5186).to_wkt(),
                'geoTransform': [bounds[0]-spacing/2, spacing, 0, bounds[3]+spacing/2, 0, -spacing],
                'values': values, 'sourceFiles': dict(source_files),
                'verticalReference': vertical_reference, 'noDataValue': None,
                'derivation': {'method': METHOD, 'tinSha256': self.identity,
                    'sourceRecordsSha256': digest(self.records), 'supportTriangleIndexes': supports,
                    'calculationSpacingM': spacing, 'sourceResolutionM': None}}


def surface_from_contours(grid, specification):
    derivation = grid.get('derivation', {})
    require(derivation.get('method') == METHOD
            and len(derivation.get('supportTriangleIndexes', [])) == grid.get('width', 0)*grid.get('height', 0)
            and all(type(i) is int and i >= 0 for i in derivation.get('supportTriangleIndexes', [])),
            'CONTOUR_DERIVATION_REQUIRED')
    model = surface_from_grid(grid, specification)
    model['evidence'] = 'PUBLIC_CONTOUR_TIN_EXPLORATORY_NOT_SITE_VALIDATED'
    provenance = model['terrainProvenance']
    provenance.update(sampling=METHOD, derivation=derivation,
        limitations=['등고선 꼭짓점·표고점의 선형 보간이며 미측정 구역의 지면 추정',
            '원 등고선의 이분 세분점은 보간용 파생점이며 새 관측 자료 아님',
            '계산 격자 간격은 원 관측 해상도·정확도가 아님',
            '도로 턱·건물 차폐·배수구 형상·실제 외곽 경계 미포함',
            '제품군 미터 해석과 미확인 기준고를 보존하며 관망 높이 자동 보정 없음'])
    return model


def residual_summary(rows):
    differences = [r['differenceM'] for r in rows if r['differenceM'] is not None]
    return {'count': len(rows), 'supported': len(differences), 'unsupported': len(rows)-len(differences),
            'meanM': math.fsum(differences)/len(differences) if differences else None,
            'rmseM': math.sqrt(math.fsum(d*d for d in differences)/len(differences)) if differences else None,
            'maximumAbsoluteM': max(map(abs, differences), default=None)}
