"""공개 문헌의 설계 제원과 SWMM 입력 단위 연결."""
import copy
import hashlib
import json
import math
from functools import lru_cache
from .swmm import ROOT, SimulationQualityError

CATALOG_SHA256 = '115d89e1935be403989a08c81111a06d081ccbc422729ace2b57cd75a46cebb9'
CATALOG_PATH = ROOT/'backend/src/main/resources/facilities/epa-designs-v1.json'


@lru_cache(maxsize=1)
def catalog():
    raw = CATALOG_PATH.read_bytes()
    if hashlib.sha256(raw).hexdigest() != CATALOG_SHA256:
        raise SimulationQualityError('LIVE_FACILITY_CATALOG_INVALID')
    return json.loads(raw)


def design_set():
    return {'id': catalog()['id'], 'sha256': CATALOG_SHA256}


def native_soil_boundary(cell, hydrology):
    physical = cell.get('physicalInputs', {})
    rate = physical.get('conductivityMmH', hydrology['conductivityMmH'])
    if (cell.get('kind') != 'GROUND' or 'RAIN_GARDEN' not in cell['allowedTypes']
            or isinstance(rate, bool) or not isinstance(rate, (int, float))
            or not math.isfinite(rate) or rate <= 0):
        raise SimulationQualityError('LIVE_NATIVE_SOIL_BOUNDARY_INVALID')
    return {'method': 'RG_NATIVE_SOIL_SEEPAGE_V1', 'seepageMmH': rate,
            'basis': ('TEXTURE_CLASS_LITERATURE_ESTIMATE'
                      if physical.get('soilStatus') == 'TEXTURE_CLASS_LITERATURE_ESTIMATE'
                      and 'conductivityMmH' in physical else 'UNRESOLVED_DESIGN_ASSUMPTION'),
            'liner': 'UNLINED_DESIGN_NOT_SITE_CONFIRMED', 'storageThicknessMm': 0}


def apply(source, model):
    if model.get('facilityDesignSet') != design_set():
        raise SimulationQualityError('LIVE_FACILITY_DESIGN_INVALID')
    cell = model['cells'][0]
    physical = cell.get('physicalInputs', {})
    slope = physical.get('slopePercent', model['hydrology']['slopePercent'])
    native_k = physical.get('conductivityMmH', model['hydrology']['conductivityMmH'])
    boundary = physical.get('rainGardenBoundary')
    if boundary is not None and boundary != native_soil_boundary(cell, model['hydrology']):
        raise SimulationQualityError('LIVE_NATIVE_SOIL_BOUNDARY_INVALID')
    rows = []
    for profile in catalog()['profiles'].values():
        t = profile['type']
        p = {k: v['value'] for k, v in profile['parameters'].items()}
        rows += [f'{t} {t}', f'{t} SURFACE {p["surfaceDepthMm"]} {p["vegetationFraction"]} {p["surfaceRoughness"]} {slope} 0']
        if 'soilDepthMm' in p:
            rows.append(f'{t} SOIL {p["soilDepthMm"]} {p["porosity"]} {p["fieldCapacity"]} {p["wiltingPoint"]} {p["conductivityMmH"]} {p["conductivitySlope"]} {p["suctionMm"]}')
        if t == 'PP':
            # SWMM 포장·저류층 입력은 공극률이 아닌 공극비 e=φ/(1-φ).
            void_ratio = p['pavementPorosity']/(1-p['pavementPorosity'])
            rows.append(f'PP PAVEMENT {p["pavementDepthMm"]} {void_ratio} {p["imperviousFraction"]} {p["conductivityMmH"]} {p["cloggingFactor"]}')
            void_ratio = p['storagePorosity']/(1-p['storagePorosity'])
            rows.append(f'PP STORAGE {p["storageDepthMm"]} {void_ratio} {native_k} 0')
        if t == 'GR':
            rows.append(f'GR DRAINMAT {p["drainageDepthMm"]} {p["drainagePorosity"]} {p["drainageRoughness"]}')
        if t == 'RG' and boundary is not None:
            # 두께·공극 체적을 늘리지 않고 EPA 하부 침투 경계만 연결한다.
            rows.append(f'RG STORAGE 0 0 {boundary["seepageMmH"]} 0')
    lines, section = [], ''
    for line in source.splitlines():
        if line.startswith('['):
            section = line
            lines.append(line)
            if section == '[LID_CONTROLS]':
                lines.extend(rows)
        elif section != '[LID_CONTROLS]':
            lines.append(line)
    return '\n'.join(lines)+'\n'


def evidence(facility, model=None):
    source = catalog()
    value = copy.deepcopy({'catalogSha256': CATALOG_SHA256, 'evidence': source['evidence'],
                          'source': source['source'], 'profile': source['profiles'][facility],
                          'limitations': source['limitations']})
    if facility == 'RAIN_GARDEN' and model is not None:
        boundary = model['cells'][0].get('physicalInputs', {}).get('rainGardenBoundary')
        if boundary is not None:
            value['nativeSoilBoundary'] = copy.deepcopy(boundary)
    return value
