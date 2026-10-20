"""현장 결측과 구분되는 공개 문헌의 고정 비교 조건."""
import hashlib
import json
import math
from functools import lru_cache

from ..engine.swmm import ROOT, SimulationQualityError

PATH = ROOT / 'backend/src/main/resources/facilities/reference-surfaces-v1.json'
SHA256 = '164358be09db34872324d63ce10df84a23cac936e5f5a8c0dc5fb12d0269b1bc'
SOIL_STATUS = 'PUBLIC_REFERENCE_SCENARIO'
SLOPE_METHOD = 'PUBLIC_REFERENCE_SURFACE_SCENARIO'
BASIS = 'PUBLIC_REFERENCE_SCENARIO_NOT_LOCAL_MEASUREMENT'


@lru_cache(maxsize=1)
def catalog():
    raw = PATH.read_bytes()
    if hashlib.sha256(raw).hexdigest() != SHA256:
        raise SimulationQualityError('REFERENCE_SURFACE_CATALOG_INVALID')
    value = json.loads(raw)
    soil = value['soilScenario']
    if (not math.isclose(soil['conductivityMmH'], soil['conductivityInH'] * 25.4, abs_tol=1e-12)
            or not math.isclose(soil['suctionMm'], soil['suctionIn'] * 25.4, abs_tol=1e-12)
            or not math.isclose(soil['initialMoistureDeficit'], soil['porosity'] - soil['fieldCapacity'], abs_tol=1e-12)):
        raise SimulationQualityError('REFERENCE_SURFACE_UNITS_INVALID')
    return value


def reference():
    return {'id': catalog()['id'], 'sha256': SHA256}


def surface_scenario(cell, land_use):
    if cell.get('kind') == 'ROOF' and cell.get('role') == 'BUILDING_FOOTPRINT':
        return 'ROOF_REFERENCE'
    if cell.get('kind') == 'GROUND':
        if cell.get('role') in ('ROAD_AREA', 'SIDEWALK_AREA', 'PARKING_AREA'):
            return 'PAVEMENT_REFERENCE'
        if cell.get('role') == 'CULTIVATION_LANDSCAPE_AREA':
            if land_use == '밭':
                return 'DRY_CULTIVATION_REFERENCE'
            if land_use in ('과수원', '목초지'):
                return 'GRASS_REFERENCE'
    return None


def validate(cell):
    physical = cell.get('physicalInputs', {})
    if not isinstance(physical, dict):
        raise SimulationQualityError('REFERENCE_SURFACE_INPUT_INVALID')
    value = catalog()
    surface = value['surfaceScenarios'].get(physical.get('surfaceScenarioId'))
    if (physical.get('referenceScenario') != reference() or surface is None
            or physical.get('surfaceScenarioId') != surface_scenario(cell, cell.get('sourceLandUse'))
            or physical.get('slopeMethod') != SLOPE_METHOD
            or physical.get('slopePercent') != value['slopeScenario']['valuePercent']):
        raise SimulationQualityError('REFERENCE_SURFACE_INPUT_INVALID')
    expected = {key: surface[key] for key in ('imperviousPercent', 'nImpervious', 'nPervious',
                                            'depressionMm', 'depressionPerviousMm')}
    if cell.get('kind') == 'GROUND':
        soil = value['soilScenario']
        if physical.get('soilStatus') != SOIL_STATUS:
            raise SimulationQualityError('REFERENCE_SURFACE_SOIL_INVALID')
        expected.update(conductivityMmH=soil['conductivityMmH'], suctionMm=soil['suctionMm'],
                        initialMoistureDeficit=soil['initialMoistureDeficit'])
    elif cell.get('kind') != 'ROOF' or physical.get('soilStatus') != 'NOT_APPLICABLE_ROOF':
        raise SimulationQualityError('REFERENCE_SURFACE_SOIL_INVALID')
    if any(type(physical.get(key)) not in (int, float) or not math.isfinite(physical[key])
           or not math.isclose(physical[key], expected_value, abs_tol=1e-12, rel_tol=1e-12)
           for key, expected_value in expected.items()):
        raise SimulationQualityError('REFERENCE_SURFACE_PARAMETERS_INVALID')


def is_reference_soil(cell):
    physical = cell.get('physicalInputs', {})
    if not isinstance(physical, dict) or physical.get('soilStatus') != SOIL_STATUS:
        return False
    validate(cell)
    return True
