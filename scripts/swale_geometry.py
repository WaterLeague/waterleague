"""공개 도형 내부의 고정 폭 직선 설계와 보수적인 길이 한도."""
import math
from shapely.geometry import Polygon


def contained_design(cell):
    physical = cell.get('physicalInputs', {})
    if (cell['kind'] != 'GROUND'
            or physical.get('soilStatus') != 'TEXTURE_CLASS_LITERATURE_ESTIMATE'
            or physical.get('slopeMethod') != 'NGII_2025_90M_HORN_TERRAIN_PROXY'
            or not .5 <= physical.get('slopePercent', -1) <= 3):
        return None
    polygon = Polygon(cell['coordinates'])
    if not polygon.is_valid or polygon.is_empty:
        return None
    corners = list(polygon.minimum_rotated_rectangle.exterior.coords)
    edges = [(b[0]-a[0], b[1]-a[1]) for a, b in zip(corners, corners[1:])]
    dx, dy = max(edges, key=lambda e: math.hypot(*e))
    norm = math.hypot(dx, dy)
    dx, dy = dx/norm, dy/norm
    if dx < 0 or (dx == 0 and dy < 0):
        dx, dy = -dx, -dy
    center = polygon.representative_point()
    def rectangle(length):
        return [[center.x+dx*s*length/2-dy*t, center.y+dy*s*length/2+dx*t]
                for s, t in ((-1,-1), (1,-1), (1,1), (-1,1), (-1,-1))]
    low, high = 0., norm
    for _ in range(48):
        mid = (low+high)/2
        if polygon.covers(Polygon(rectangle(mid))):
            low = mid
        else:
            high = mid
    area = math.floor(min(low*2, cell['maxAreaM2'])*100)/100
    if area < .01:
        return None
    length = area/2
    coordinates = rectangle(length)
    if not polygon.covers(Polygon(coordinates)):
        return None
    return {'method': 'CONTAINED_FIXED_WIDTH_STRAIGHT_DESIGN_V1', 'topWidthM': 2,
            'maxLengthM': length, 'maxAreaM2': area, 'center': [center.x, center.y],
            'direction': [dx, dy], 'coordinates': coordinates,
            'slopeBasis': 'REGIONAL_TERRAIN_PROXY_NOT_LONGITUDINAL_SURVEY',
            'outlet': 'SURFACE_RUNOFF_UNCONNECTED_TO_NETWORK'}
