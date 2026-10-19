"""원형 설계 영역에 공개 시설·공통 비교 조건을 결속."""
from decimal import Decimal, InvalidOperation

from ..engine.facilities import bioretention_boundary, native_soil_boundary, trench_boundary
from . import reference_conditions as reference
from .design_footprint import contained_rectangle
from .geometry import cell_geometry, dimensions

FACILITY_ORDER = ('RAIN_GARDEN', 'PERMEABLE_PAVEMENT', 'GREEN_ROOF', 'BIORETENTION',
                  'VEGETATIVE_SWALE', 'INFILTRATION_TRENCH')


def hydrology():
    value = reference.catalog()
    soil = value['soilScenario']
    surface = value['surfaceScenarios']['PAVEMENT_REFERENCE']
    return {'imperviousPercent': surface['imperviousPercent'], 'slopePercent': value['slopeScenario']['valuePercent'],
        'nImpervious': surface['nImpervious'], 'depressionMm': surface['depressionMm'],
        'suctionMm': soil['suctionMm'], 'conductivityMmH': soil['conductivityMmH'],
        'moistureDeficit': soil['initialMoistureDeficit'], 'evaporationMmDay': 0,
        'initialSaturationPercent': 0}


def display_height(properties):
    try:
        floors = Decimal(properties.get('층수') or '')
        if floors.is_finite() and 0 < floors <= 200 and floors == int(floors):
            return float(floors) * 3.2, 'FLOOR_COUNT_DISPLAY_ASSUMPTION'
    except (InvalidOperation, TypeError, ValueError):
        pass
    return .3, 'UNKNOWN_HEIGHT_FLAT_DISPLAY'


def bind(cell, properties):
    geometry = cell_geometry(cell)
    scenario = reference.surface_scenario(cell, properties.get('구분'))
    if scenario == 'ROOF_REFERENCE':
        types = ['GREEN_ROOF']
    elif scenario == 'PAVEMENT_REFERENCE':
        types = ['PERMEABLE_PAVEMENT']
    elif scenario in ('DRY_CULTIVATION_REFERENCE', 'GRASS_REFERENCE'):
        types = ['RAIN_GARDEN', 'BIORETENTION']
    else:
        return {'status': 'UNSUPPORTED_SURFACE_PROCESS', 'reason': 'PADDY_FORESTRY_OR_UNRESOLVED_SURFACE',
                'allowedTypes': [], 'sourceLandUse': properties.get('구분'), 'constructionEligibility': 'UNKNOWN'}
    value = reference.catalog()
    physical = dimensions(geometry) | {key: value['surfaceScenarios'][scenario][key]
        for key in ('imperviousPercent', 'nImpervious', 'nPervious', 'depressionMm', 'depressionPerviousMm')}
    physical.update(referenceScenario=reference.reference(), surfaceScenarioId=scenario,
        slopePercent=value['slopeScenario']['valuePercent'], slopeMethod=reference.SLOPE_METHOD,
        surfaceTag=None, imperviousBasis='PUBLIC_REFERENCE_SURFACE_SCENARIO_NOT_SURVEY',
        soilStatus='NOT_APPLICABLE_ROOF' if cell['kind'] == 'ROOF' else reference.SOIL_STATUS,
        localSoilStatus='UNRESOLVED', localSlopeStatus='UNRESOLVED', localMaterialStatus='UNRESOLVED',
        geometrySourceIds=[cell['sourceObjectId']])
    if cell['kind'] == 'GROUND':
        soil = value['soilScenario']
        physical.update(conductivityMmH=soil['conductivityMmH'], suctionMm=soil['suctionMm'],
                        initialMoistureDeficit=soil['initialMoistureDeficit'])
    candidate = cell | {'allowedTypes': types, 'physicalInputs': physical, 'sourceLandUse': properties.get('구분')}
    if 'RAIN_GARDEN' in types:
        physical['rainGardenBoundary'] = native_soil_boundary(candidate, hydrology())
        physical['bioretentionBoundary'] = bioretention_boundary(candidate)
        swale = contained_rectangle(candidate, 2, 'PUBLIC_DESIGN_SLOPE_NOT_SURVEY')
        if swale is not None:
            physical['swaleDesign'] = swale
            types.append('VEGETATIVE_SWALE')
        trench = contained_rectangle(candidate, 1, 'LEVEL_STORAGE_DESIGN_NOT_SURVEY')
        if trench is not None:
            physical['trenchDesign'] = trench
            types.append('INFILTRATION_TRENCH')
            physical['trenchBoundary'] = trench_boundary(candidate)
    center = geometry.representative_point()
    height, height_basis = display_height(properties) if cell['kind'] == 'ROOF' else (.05, 'GROUND_DISPLAY_OFFSET')
    return {'status': 'EXPLORATORY_REFERENCE_SCENARIO', 'allowedTypes': types,
        'physicalInputs': physical, 'centerProjected': [center.x, center.y],
        'heightM': height, 'heightBasis': height_basis, 'siteEligibility': 'UNKNOWN',
        'areaLimitBasis': 'PUBLIC_NATIVE_DESIGN_GEOMETRY', 'inflowPolicy': 'DIRECT_RAINFALL_ONLY',
        'sourceLandUse': properties.get('구분'), 'constructionEligibility': 'UNKNOWN'}
