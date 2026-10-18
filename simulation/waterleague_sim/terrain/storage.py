"""선형 삼각 지형과 수평 수면 사이의 잠긴 면적·체적 적분."""
import hashlib
import math
from pathlib import Path

from waterleague_sim.engine.flood_errors import require
from waterleague_sim.terrain.grid import digest, finite

METHOD = 'PIECEWISE_LINEAR_TERRAIN_HORIZONTAL_STAGE_INTEGRAL_V1'
REFERENCE = 'https://doc.esri.com/en/arcgis-pro/latest/tool-reference/3d-analyst/tin-polygon-volume.html'


def triangle_storage(area, heights, stage):
    require(finite(area) and area > 0 and finite(stage) and isinstance(heights, (list, tuple)) and len(heights) == 3
            and all(map(finite, heights)), 'STORAGE_TRIANGLE_INVALID')
    low, middle, high = sorted(heights)
    if stage <= low:
        return 0., 0.
    if stage >= high:
        return area, area * math.fsum(stage - z for z in heights) / 3
    span = high - low
    if stage < middle:
        depth = stage - low
        fraction = (depth / (middle - low)) * (depth / span)
        wet_area = area * fraction
        return wet_area, wet_area * depth / 3
    # 상단 삼각형을 빼는 방식의 큰 수 상쇄를 피하고 중간 높이부터 적분한다.
    lower, upper, rise = middle - low, high - middle, stage - middle
    ratio = rise / upper
    wet_area = area * (lower / span + rise / span * (2 - ratio))
    volume = area * (lower / span * lower / 3 + lower / span * rise
                     + rise / span * rise * (1 - ratio / 3))
    return wet_area, volume


def stage_storage(surface, cells, stages):
    require(isinstance(surface, dict), 'STORAGE_SURFACE_INVALID')
    points, triangles, elevations = (surface.get(k) for k in ('verticesM', 'triangles', 'elevationM'))
    require(isinstance(points, list) and isinstance(triangles, list) and isinstance(elevations, list)
            and len(points) == len(elevations) and 3 <= len(points) <= 500_000
            and 1 <= len(triangles) <= 200_000, 'STORAGE_SURFACE_INVALID')
    require(isinstance(cells, list) and cells
            and all(type(i) is int and 0 <= i < len(triangles) for i in cells)
            and len(set(cells)) == len(cells), 'STORAGE_CELLS_INVALID')
    require(isinstance(stages, list) and 1 <= len(stages) <= 512 and all(map(finite, stages))
            and all(a < b for a, b in zip(stages, stages[1:]))
            and len(stages) * len(cells) <= 20_000_000, 'STORAGE_STAGES_INVALID')
    selected, unique = [], set()
    for cell in sorted(cells):
        tri = triangles[cell]
        require(isinstance(tri, list) and len(tri) == 3
                and all(type(i) is int and 0 <= i < len(points) for i in tri)
                and len(set(tri)) == 3 and tuple(sorted(tri)) not in unique, 'STORAGE_TRIANGLE_INVALID')
        unique.add(tuple(sorted(tri)))
        coordinates, heights = [points[i] for i in tri], [elevations[i] for i in tri]
        require(all(isinstance(p, list) and len(p) == 2 and all(map(finite, p)) for p in coordinates)
                and all(map(finite, heights)), 'STORAGE_TRIANGLE_INVALID')
        a, b, c = coordinates
        area = ((b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]))/2
        require(finite(area) and area > 0, 'STORAGE_TRIANGLE_INVALID')
        selected.append({'cell': cell, 'coordinatesM': coordinates, 'elevationsM': heights, 'areaM2': area})
    rows = []
    for stage in stages:
        values = [triangle_storage(t['areaM2'], t['elevationsM'], stage) for t in selected]
        volume = math.fsum(v for _, v in values)
        centroid = math.fsum(t['areaM2'] * max(0., math.fsum(stage-z for z in t['elevationsM'])/3)
                             for t in selected)
        rows.append({'stageM': stage, 'wettedPlanAreaM2': math.fsum(a for a, _ in values),
                     'storageM3': volume, 'centroidStorageM3': centroid,
                     'linearMinusCentroidStorageM3': volume-centroid})
    require(all(all(finite(v) for v in row.values()) for row in rows), 'STORAGE_RESULT_NONFINITE')
    return {'schemaVersion': 1, 'method': METHOD, 'sourceReference': REFERENCE,
            'sourceGeometrySha256': digest(selected), 'triangles': sorted(cells),
            'planAreaM2': math.fsum(t['areaM2'] for t in selected), 'levels': rows,
            'implementationSha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'hydraulicConnectivityVerified': False, 'rankingEligible': False,
            'limitations': ['원 DEM 또는 설계 꼭짓점 사이 선형 보간 지형의 기하 적분이며 현장 용량 실측 아님',
                '수평 수면 아래 모든 선택 영역의 체적이며 연결되지 않은 함몰의 채움 순서 미반영',
                '계산 엔진의 격자 중심 저장량·수지·수심을 이 기하 적분으로 치환하지 않음',
                '배수 경계·유입량·관망·침투를 포함한 수리 계산 또는 침수 예측이 아님']}
