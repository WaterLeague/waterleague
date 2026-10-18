"""공개 도형 안에 포함되는 고정 폭 직선 배치."""
import math
from shapely.geometry import Polygon

def contained_rectangle(cell, width, slope_basis):
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
        return [[center.x+dx*s*length/2-dy*t*width/2, center.y+dy*s*length/2+dx*t*width/2]
                for s, t in ((-1,-1), (1,-1), (1,1), (-1,1), (-1,-1))]
    low, high = 0., norm
    for _ in range(48):
        mid = (low+high)/2
        if polygon.covers(Polygon(rectangle(mid))):
            low = mid
        else:
            high = mid
    area = math.floor(min(low*width, cell['maxAreaM2'])*100)/100
    if area < .01:
        return None
    length = area/width
    coordinates = rectangle(length)
    if not polygon.covers(Polygon(coordinates)):
        return None
    return {'method': 'CONTAINED_FIXED_WIDTH_STRAIGHT_DESIGN_V1', 'topWidthM': width,
            'maxLengthM': length, 'maxAreaM2': area, 'center': [center.x, center.y],
            'direction': [dx, dy], 'coordinates': coordinates,
            'slopeBasis': slope_basis,
            'outlet': 'SURFACE_RUNOFF_UNCONNECTED_TO_NETWORK'}
