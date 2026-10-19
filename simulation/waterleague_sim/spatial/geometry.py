"""미터 원 도형의 구멍·다중 면·면적을 보존하는 계산 경계."""
from decimal import Decimal, ROUND_FLOOR
import math

import shapely
from shapely.geometry import shape


class SiteGeometryError(ValueError):
    pass


def polygon_geometry(value):
    try:
        if value['type'] == 'Polygon':
            polygons = [value['coordinates']]
        elif value['type'] == 'MultiPolygon':
            polygons = value['coordinates']
        else:
            raise SiteGeometryError('SITE_POLYGON_TYPE_INVALID')
        if not isinstance(polygons, (list, tuple)) or not 1 <= len(polygons) <= 1000:
            raise SiteGeometryError('SITE_POLYGON_PARTS_INVALID')
        points = 0
        for polygon in polygons:
            if not isinstance(polygon, (list, tuple)) or not 1 <= len(polygon) <= 500:
                raise SiteGeometryError('SITE_POLYGON_RINGS_INVALID')
            for ring in polygon:
                if not isinstance(ring, (list, tuple)) or not 4 <= len(ring) <= 20000:
                    raise SiteGeometryError('SITE_POLYGON_RING_INVALID')
                points += len(ring)
                if points > 1_000_000 or ring[0] != ring[-1]:
                    raise SiteGeometryError('SITE_POLYGON_RING_INVALID')
                for point in ring:
                    if (not isinstance(point, (list, tuple)) or len(point) != 2
                            or any(type(v) not in (int, float) or not math.isfinite(v)
                                   or abs(v) > 10_000_000 for v in point)):
                        raise SiteGeometryError('SITE_POLYGON_COORDINATE_INVALID')
        geometry = shape(value)
        if geometry.is_empty or not geometry.is_valid or geometry.area <= 0:
            raise SiteGeometryError('SITE_POLYGON_INVALID')
        return geometry
    except SiteGeometryError:
        raise
    except (KeyError, TypeError, ValueError, shapely.errors.ShapelyError):
        raise SiteGeometryError('SITE_POLYGON_INVALID') from None


def cell_geometry(cell):
    if 'geometry' in cell:
        value = cell['geometry']
    else:
        # 과거 수치 재현 모델의 단일 외곽선도 같은 검사에서 해석한다.
        value = {'type': 'Polygon', 'coordinates': [cell.get('coordinates')]}
    geometry = polygon_geometry(value)
    area = cell.get('areaM2')
    if (type(area) not in (int, float) or not math.isfinite(area) or area <= 0
            or not math.isclose(geometry.area, area, rel_tol=1e-10, abs_tol=1e-6)):
        raise SiteGeometryError('SITE_POLYGON_AREA_MISMATCH')
    return geometry


def dimensions(geometry):
    if geometry.geom_type not in ('Polygon', 'MultiPolygon') or not geometry.is_valid or geometry.area <= 0:
        raise SiteGeometryError('SITE_FLOW_DIMENSIONS_INVALID')
    rectangle = geometry.minimum_rotated_rectangle
    points = list(rectangle.exterior.coords)
    length = max(math.dist(a, b) for a, b in zip(points, points[1:]))
    if length <= 0:
        raise SiteGeometryError('SITE_FLOW_DIMENSIONS_INVALID')
    return {'flowLengthM': length, 'runoffWidthM': geometry.area / length,
            'widthMethod': 'FOOTPRINT_AREA_OVER_LONG_AXIS'}


def area_limit(geometry):
    return Decimal(str(geometry.area)).quantize(Decimal('.01'), rounding=ROUND_FLOOR)
