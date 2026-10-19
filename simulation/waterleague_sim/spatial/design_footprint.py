"""구멍과 분리된 면을 넘지 않는 고정 폭 시설 설계."""
import math

from shapely.geometry import Polygon

from .geometry import SiteGeometryError, cell_geometry

METHOD = 'CONTAINED_COMPONENT_RECTANGLE_V2'


def contained_rectangle(cell, width, slope_basis):
    geometry = cell_geometry(cell)
    parts = [geometry] if geometry.geom_type == 'Polygon' else list(geometry.geoms)
    polygon = sorted(parts, key=lambda g: (-g.area, g.wkb))[0]
    corners = list(polygon.minimum_rotated_rectangle.exterior.coords)
    dx, dy = max(((b[0] - a[0], b[1] - a[1]) for a, b in zip(corners, corners[1:])),
                 key=lambda d: math.hypot(*d))
    norm = math.hypot(dx, dy)
    dx, dy = dx / norm, dy / norm
    if dx < 0 or (dx == 0 and dy < 0):
        dx, dy = -dx, -dy
    center = polygon.representative_point()

    def coordinates(length):
        return [[center.x + dx * s * length / 2 - dy * t * width / 2,
                 center.y + dy * s * length / 2 + dx * t * width / 2]
                for s, t in ((-1, -1), (1, -1), (1, 1), (-1, 1), (-1, -1))]

    low, high = 0., norm
    for _ in range(48):
        mid = (low + high) / 2
        if polygon.covers(Polygon(coordinates(mid))):
            low = mid
        else:
            high = mid
    area = math.floor(min(low * width, cell['maxAreaM2']) * 100) / 100
    if area < .01:
        return None
    length = area / width
    rectangle = coordinates(length)
    if not geometry.covers(Polygon(rectangle)):
        return None
    return {'method': METHOD, 'topWidthM': width, 'maxLengthM': length, 'maxAreaM2': area,
            'center': [center.x, center.y], 'direction': [dx, dy], 'coordinates': rectangle,
            'componentPolicy': 'LARGEST_AREA_THEN_WKB', 'slopeBasis': slope_basis,
            'outlet': 'SURFACE_RUNOFF_UNCONNECTED_TO_NETWORK'}


def validate(cell, design):
    geometry = cell_geometry(cell)
    try:
        ring = design['coordinates']
        if (design['method'] != METHOD or len(ring) != 5 or ring[0] != ring[-1]
                or any(len(p) != 2 or any(type(v) not in (int, float) or not math.isfinite(v) for v in p) for p in ring)):
            raise SiteGeometryError('DESIGN_RECTANGLE_INVALID')
        polygon = Polygon(ring)
        width, length = design['topWidthM'], design['maxLengthM']
        if (any(type(v) not in (int, float) or not math.isfinite(v) or v <= 0
                for v in (width, length, design['maxAreaM2']))
                or design['maxAreaM2'] > cell['maxAreaM2']
                or not polygon.is_valid or not geometry.covers(polygon)
                or not math.isclose(polygon.area, design['maxAreaM2'], abs_tol=1e-6, rel_tol=1e-10)
                or not math.isclose(width * length, design['maxAreaM2'], abs_tol=1e-8)):
            raise SiteGeometryError('DESIGN_RECTANGLE_INVALID')
        edges = [math.dist(a, b) for a, b in zip(ring, ring[1:])]
        for actual, expected in zip(edges, (length, width, length, width)):
            if not math.isclose(actual, expected, abs_tol=1e-6, rel_tol=1e-10):
                raise SiteGeometryError('DESIGN_RECTANGLE_INVALID')
        center, direction = design['center'], design['direction']
        if (len(center) != 2 or len(direction) != 2
                or any(type(v) not in (int, float) or not math.isfinite(v) for v in [*center, *direction])
                or not math.isclose(math.hypot(*direction), 1, abs_tol=1e-10)):
            raise SiteGeometryError('DESIGN_RECTANGLE_INVALID')
        for index in (0, 1):
            if (not math.isclose(center[index], math.fsum(p[index] for p in ring[:4]) / 4, abs_tol=1e-6)
                    or not math.isclose(direction[index], (ring[1][index] - ring[0][index]) / length, abs_tol=1e-6)):
                raise SiteGeometryError('DESIGN_RECTANGLE_INVALID')
    except (KeyError, TypeError, ValueError):
        raise SiteGeometryError('DESIGN_RECTANGLE_INVALID') from None
