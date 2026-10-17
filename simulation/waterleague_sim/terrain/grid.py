"""원본 래스터 중심의 높이를 보존하는 명시적 삼각 격자 구성."""
import hashlib
import json
import math
from copy import deepcopy
from pathlib import Path

from pyproj import CRS
from pyproj.exceptions import CRSError

from waterleague_sim.engine.flood_errors import require


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def surface_from_grid(grid, specification):
    require(type(grid.get('schemaVersion')) is int and grid['schemaVersion'] == 1,
            'TERRAIN_SCHEMA_INVALID')
    width, height = grid.get('width'), grid.get('height')
    require(type(width) is int and type(height) is int and width >= 2 and height >= 2
            and 2 * (width - 1) * (height - 1) <= 200_000, 'TERRAIN_DIMENSIONS_INVALID')
    transform, values = grid.get('geoTransform'), grid.get('values')
    require(isinstance(transform, list) and len(transform) == 6 and all(map(finite, transform))
            and transform[1] > 0 and transform[5] < 0 and transform[2] == transform[4] == 0,
            'TERRAIN_TRANSFORM_INVALID')
    require(isinstance(values, list) and len(values) == width * height
            and all(finite(v) and v != grid.get('noDataValue') for v in values),
            'TERRAIN_HEIGHT_MISSING')
    reference = grid.get('verticalReference')
    require(isinstance(reference, dict) and reference.get('unit') == 'm'
            and reference.get('unitStatus') in ('SOURCE_CONFIRMED', 'PRODUCT_FAMILY_INFERRED')
            and reference.get('unitEvidence') and type(reference.get('datumVerified')) is bool
            and (not reference['datumVerified'] or isinstance(reference.get('datum'), str)
                 and reference['datum'].strip()), 'TERRAIN_VERTICAL_REFERENCE_REQUIRED')
    try:
        crs = CRS.from_wkt(grid['coordinateWkt'])
    except (KeyError, ValueError, TypeError, CRSError):
        require(False, 'TERRAIN_COORDINATE_REFERENCE_INVALID')
    require(crs.is_projected and len(crs.axis_info) >= 2
            and all(axis.unit_conversion_factor == 1 for axis in crs.axis_info[:2]),
            'TERRAIN_METRIC_PROJECTION_REQUIRED')
    sources = grid.get('sourceFiles')
    require(isinstance(sources, dict) and sources and all(isinstance(name, str) and name
            and isinstance(sha, str) and len(sha) == 64 and all(c in '0123456789abcdef' for c in sha)
            for name, sha in sources.items()), 'TERRAIN_PROVENANCE_REQUIRED')
    origin = [transform[0] + .5 * transform[1], transform[3] + .5 * transform[5]]
    vertices = [[column * transform[1], row * transform[5]]
                for row in range(height) for column in range(width)]
    triangles, boundary = [], []
    for row in range(height - 1):
        for column in range(width - 1):
            a, k = row * width + column, len(triangles)
            # 북쪽에서 남쪽으로 증가하는 행 순서에서 반시계 방향 유지.
            triangles.extend([[a, a + width, a + 1], [a + 1, a + width, a + width + 1]])
            if row == 0:
                boundary.append([k, 1, 'north'])
            if row == height - 2:
                boundary.append([k + 1, 0, 'south'])
            if column == 0:
                boundary.append([k, 2, 'west'])
            if column == width - 2:
                boundary.append([k + 1, 1, 'east'])
    count = len(triangles)
    roughness, initial = specification.get('manningN'), specification.get('initialDepthM')
    require(all(isinstance(field, list) and len(field) == count
                and all(finite(value) and value >= 0 for value in field) for field in (roughness, initial)),
            'TERRAIN_HYDRAULIC_FIELDS_REQUIRED')
    evidence = specification.get('evidence')
    require(isinstance(evidence, dict) and all(isinstance(evidence.get(key), str)
            and evidence[key].strip() for key in ('roughness', 'initialState', 'boundary', 'rainfallOwner')),
            'TERRAIN_FIELD_EVIDENCE_REQUIRED')
    conditions = specification.get('boundaryConditions')
    require(isinstance(conditions, dict) and set(conditions) == {'north', 'south', 'east', 'west'},
            'TERRAIN_BOUNDARY_REQUIRED')
    owners = specification.get('rainfallOwner')
    require(isinstance(owners, list) and len(owners) == count
            and all(value in ('SURFACE', 'NETWORK') for value in owners), 'TERRAIN_RAIN_OWNER_REQUIRED')
    maximum = specification.get('maxStepSeconds')
    require(finite(maximum) and 0 < maximum <= 60, 'SURFACE_MAX_STEP_REQUIRED')
    absolute = reference['datumVerified'] and reference['unitStatus'] == 'SOURCE_CONFIRMED'
    identity = digest({'coordinateWkt': grid['coordinateWkt'], 'originProjected': origin})
    return {'schemaVersion': 2, 'coordinateSystem': 'SOURCE_PROJECTED_LOCAL:' + identity,
            'verticalDatum': reference['datum'] if absolute else 'SOURCE_RELATIVE_UNVERIFIED:' + digest(reference),
            'evidence': 'PUBLIC_DEM_EXPLORATORY_NOT_SITE_VALIDATED', 'rankingEligible': False,
            'verticesM': vertices, 'triangles': triangles, 'elevationM': list(values),
            'manningN': list(roughness), 'initialDepthM': list(initial), 'rainfallOwner': list(owners),
            'maxStepSeconds': maximum, 'boundaryEdges': boundary, 'boundaryConditions': deepcopy(conditions),
            'terrainProvenance': {'gridSha256': digest(grid), 'sourceFiles': dict(sources),
                'coordinateWkt': grid['coordinateWkt'], 'originProjected': origin,
                'originalGeoTransform': list(transform), 'sourcePixelWindow': deepcopy(grid.get('sourcePixelWindow')),
                'spacingM': [transform[1], -transform[5]], 'verticalReference': deepcopy(reference),
                'absoluteVerticalReferenceVerified': absolute,
                'sampling': 'ORIGINAL_PIXEL_CENTERS_NO_RESAMPLING',
                'interpolation': 'PIECEWISE_LINEAR_TRIANGLES', 'fieldEvidence': dict(evidence),
                'generatorSha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                'limitations': ['격자 중심 간 선형 지형이며 실제 도로 턱·건물·배수구 형상 아님',
                    '입력 창의 외곽은 실제 배수 경계가 아니며 명시한 시험 경계 조건 적용',
                    '원본 함몰·높이·결측 보존 원칙; 결측 포함 창의 계산 거부',
                    '단위/기준고 근거와 조도·초기 상태·경계 가정은 별도 평가 필요']}}
