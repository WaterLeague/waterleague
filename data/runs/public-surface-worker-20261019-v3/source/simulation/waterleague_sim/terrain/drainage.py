"""원 DEM의 엄격한 하향 경로와 입력 창 외부 기여 면적 분석."""
from collections import Counter
import hashlib
import math
from pathlib import Path

from pyproj import CRS
from pyproj.exceptions import CRSError

from waterleague_sim.engine.flood_errors import require
from waterleague_sim.terrain.grid import digest, finite

METHOD = 'UNCONDITIONED_STRICT_DESCENT_D8_V1'
SOURCE = 'https://doc.arcgis.com/en/arcgis-online/analyze/how-flow-direction-works.htm'


def analyze(grid):
    width, height = grid.get('width'), grid.get('height')
    require(type(width) is int and type(height) is int and width >= 3 and height >= 3
            and width * height <= 250_000, 'DRAINAGE_DIMENSIONS_INVALID')
    values, transform = grid.get('values'), grid.get('geoTransform')
    require(isinstance(values, list) and len(values) == width * height
            and all(finite(v) for v in values), 'DRAINAGE_HEIGHT_INVALID')
    require(isinstance(transform, list) and len(transform) == 6 and all(map(finite, transform))
            and transform[1] > 0 and transform[5] < 0 and transform[2] == transform[4] == 0,
            'DRAINAGE_TRANSFORM_INVALID')
    try:
        crs = CRS.from_wkt(grid['coordinateWkt'])
    except (KeyError, ValueError, TypeError, CRSError):
        require(False, 'DRAINAGE_CRS_INVALID')
    require(crs.is_projected and len(crs.axis_info) >= 2
            and all(a.unit_conversion_factor == 1 for a in crs.axis_info[:2]),
            'DRAINAGE_METRIC_CRS_REQUIRED')
    reference = grid.get('verticalReference', {})
    require(reference.get('unit') == 'm' and reference.get('unitEvidence')
            and reference.get('unitStatus') in ('SOURCE_CONFIRMED', 'PRODUCT_FAMILY_INFERRED'),
            'DRAINAGE_VERTICAL_UNIT_REQUIRED')
    sources = grid.get('sourceFiles')
    require(isinstance(sources, dict) and sources and all(isinstance(k, str) and k
            and isinstance(v, str) and len(v) == 64 and all(c in '0123456789abcdef' for c in v)
            for k, v in sources.items()), 'DRAINAGE_SOURCE_REQUIRED')
    size = len(values)
    valid = [v != grid.get('noDataValue') for v in values]
    require(any(valid), 'DRAINAGE_EMPTY_GRID')
    successors, status = [None] * size, ['NODATA'] * size
    distances = {(dr, dc): math.hypot(dc * transform[1], dr * transform[5])
                 for dr in (-1, 0, 1) for dc in (-1, 0, 1) if dr or dc}
    for i, z in enumerate(values):
        if not valid[i]:
            continue
        r, c = divmod(i, width)
        # 미확보 이웃을 낮은 출구나 높은 벽으로 대체하지 않는다.
        if r in (0, height - 1) or c in (0, width - 1):
            status[i] = 'TILE_EDGE_UNRESOLVED'
            continue
        neighbors = [(i + dr * width + dc, length) for (dr, dc), length in distances.items()]
        if any(not valid[j] for j, _ in neighbors):
            status[i] = 'NODATA_NEIGHBOR_UNRESOLVED'
            continue
        slopes = [(j, (z - values[j]) / length) for j, length in neighbors if values[j] < z]
        if not slopes:
            status[i] = ('FLAT_UNRESOLVED' if any(values[j] == z for j, _ in neighbors)
                         else 'DEPRESSION_UNRESOLVED')
            continue
        largest = max(s for _, s in slopes)
        tied = [j for j, s in slopes if math.isclose(s, largest, rel_tol=1e-12, abs_tol=0)]
        if len(tied) != 1:
            status[i] = 'EQUAL_SLOPE_UNRESOLVED'
            continue
        successors[i], status[i] = tied[0], 'STRICT_DESCENT'
    ordered = sorted((i for i in range(size) if valid[i]), key=lambda i: (-values[i], i))
    counts = [int(v) for v in valid]
    for i in ordered:
        target = successors[i]
        if target is not None:
            require(values[target] < values[i], 'DRAINAGE_NON_DESCENDING_LINK')
            counts[target] += counts[i]
    terminals = [None] * size
    for i in reversed(ordered):
        target = successors[i]
        terminals[i] = i if target is None else terminals[target]
    ends = [i for i in ordered if successors[i] is None]
    require(sum(counts[i] for i in ends) == len(ordered), 'DRAINAGE_AREA_PARTITION_INVALID')
    area = transform[1] * -transform[5]
    return {'schemaVersion': 1, 'method': METHOD,
        'classification': 'DEM_DERIVED_DRAINAGE_SCREENING_NOT_HYDRAULIC_BOUNDARY',
        'rankingEligible': False, 'sourceGridSha256': digest(grid), 'sourceFiles': dict(sources),
        'sourceReference': SOURCE, 'implementationSha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'width': width, 'height': height, 'cellAreaM2': area,
        'successorCell': successors, 'status': status, 'terminalCell': terminals,
        'contributingCellsIncludingSelf': counts,
        'summary': {'validCells': len(ordered), 'noDataCells': size - len(ordered),
            'validAreaM2': len(ordered) * area, 'statusCounts': dict(sorted(Counter(status).items())),
            'terminalContributingCells': sum(counts[i] for i in ends),
            'terminalCount': len(ends), 'originalElevationsChanged': False},
        'tiePolicy': {'relativeSlopeTolerance': 1e-12, 'resolution': 'UNRESOLVED_NO_TIE_BREAK'},
        'limitations': ['8이웃의 원 고도 하향 방향이며 2D 운동량·수심·역류 계산 아님',
            '함몰 채움·암거 관통·평탄부 기울기·임의 경사 동률 해소 없음',
            'DEM 타일 외곽·결측 이웃·함몰·평탄부·동률에서 경로 중지; 실제 배수구로 취급하지 않음',
            '원 DEM 해상도·수직 단위 근거의 한계 유지; 도시 배수관·건물·도로 턱 미반영',
            '기여 면적은 미해결 경로를 제외한 이 알고리즘의 면적이며 완전한 실제 집수면적 아님',
            '이 경계를 수리 모형의 벽·자유 방류 경계로 자동 적용하지 않음']}


def window_context(grid, analysis, window):
    require(analysis.get('sourceGridSha256') == digest(grid)
            and analysis.get('method') == METHOD, 'DRAINAGE_GRID_BINDING_INVALID')
    width, height = analysis['width'], analysis['height']
    require(isinstance(window, list) and len(window) == 4 and all(type(v) is int for v in window),
            'DRAINAGE_WINDOW_INVALID')
    x, y, w, h = window
    require(x >= 0 and y >= 0 and w > 0 and h > 0 and x + w <= width and y + h <= height,
            'DRAINAGE_WINDOW_INVALID')
    selected = {r * width + c for r in range(y, y + h) for c in range(x, x + w)}
    require(all(analysis['status'][i] != 'NODATA' for i in selected), 'DRAINAGE_WINDOW_NODATA')
    successors, values = analysis['successorCell'], grid['values']
    reaches = [False] * len(values)
    for i in sorted(range(len(values)), key=lambda i: (values[i], i)):
        target = successors[i]
        reaches[i] = i in selected or target is not None and reaches[target]
    incoming, outgoing = [], []
    for i, target in enumerate(successors):
        if target is None:
            continue
        if i not in selected and target in selected:
            incoming.append([i, target])
        elif i in selected and target not in selected:
            outgoing.append([i, target])
    outside = [i for i, v in enumerate(reaches) if v and i not in selected]
    surrounding = set()
    for i, reached in enumerate(reaches):
        if not reached:
            continue
        r, c = divmod(i, width)
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if 0 <= r + dr < height and 0 <= c + dc < width:
                    j = (r + dr) * width + c + dc
                    if analysis['status'][j] != 'STRICT_DESCENT':
                        surrounding.add(j)
    return {'sourceGridSha256': analysis['sourceGridSha256'], 'analysisSha256': digest(analysis),
        'sourcePixelWindow': list(window), 'rasterCells': len(selected),
        'rasterFootprintAreaM2': len(selected) * analysis['cellAreaM2'],
        'areaConvention': 'RASTER_CELL_FOOTPRINT_NOT_CENTER_TO_CENTER_TRIANGLE_MESH',
        'incomingLinks': incoming, 'outgoingLinks': outgoing,
        'outsideContributingCells': outside,
        'outsideContributingAreaM2': len(outside) * analysis['cellAreaM2'],
        'unresolvedWindowCellCounts': dict(sorted(Counter(analysis['status'][i]
            for i in selected if analysis['status'][i] != 'STRICT_DESCENT').items())),
        'adjacentUnresolvedCellCounts': dict(sorted(Counter(analysis['status'][i] for i in surrounding).items())),
        'completeWatershedVerified': False, 'hydraulicBoundaryAdmissible': False}
