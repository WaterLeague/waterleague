"""공개 문헌의 설계 제원과 SWMM 입력 단위 연결."""
import copy
import hashlib
import json
import math
from functools import lru_cache
from .swmm import ROOT, SimulationQualityError

CATALOG_SHA256 = '115d89e1935be403989a08c81111a06d081ccbc422729ace2b57cd75a46cebb9'
CATALOG_PATH = ROOT/'backend/src/main/resources/facilities/epa-designs-v1.json'
CATALOG_V2_SHA256 = '068094e1fb8214c60a86bcbc64e039964ba771beb90400702d34f6b741e2d987'
CATALOG_V2_PATH = ROOT/'backend/src/main/resources/facilities/epa-designs-v2.json'


@lru_cache(maxsize=2)
def catalog(version=1):
    raw = (CATALOG_PATH if version == 1 else CATALOG_V2_PATH).read_bytes()
    if version not in (1, 2) or hashlib.sha256(raw).hexdigest() != (CATALOG_SHA256 if version == 1 else CATALOG_V2_SHA256):
        raise SimulationQualityError('LIVE_FACILITY_CATALOG_INVALID')
    return json.loads(raw)


def design_set(version=1):
    return {'id': catalog(version)['id'], 'sha256': CATALOG_SHA256 if version == 1 else CATALOG_V2_SHA256}


def model_version(model):
    for version, digest in ((1, CATALOG_SHA256), (2, CATALOG_V2_SHA256)):
        if model.get('facilityDesignSet') == {'id': f'EPA_LID_PUBLIC_DESIGNS_V{version}', 'sha256': digest}:
            return version
    raise SimulationQualityError('LIVE_FACILITY_DESIGN_INVALID')


def source_path(model):
    return CATALOG_PATH if model_version(model) == 1 else CATALOG_V2_PATH


def bioretention_boundary(cell):
    physical = cell.get('physicalInputs', {})
    rate = physical.get('conductivityMmH')
    if (cell.get('kind') != 'GROUND' or physical.get('soilStatus') != 'TEXTURE_CLASS_LITERATURE_ESTIMATE'
            or type(rate) not in (int, float) or not math.isfinite(rate) or rate <= 0):
        raise SimulationQualityError('LIVE_BIORETENTION_BOUNDARY_INVALID')
    return {'method': 'BC_NATIVE_SOIL_SEEPAGE_V1', 'seepageMmH': rate,
            'basis': 'TEXTURE_CLASS_LITERATURE_ESTIMATE', 'liner': 'UNLINED_DESIGN_NOT_SITE_CONFIRMED',
            'storageThicknessMm': 304.8, 'underdrain': 'NONE_DIRECT_RAIN_INFILTRATION_DESIGN'}


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
    version = model_version(model)
    cell = model['cells'][0]
    physical = cell.get('physicalInputs', {})
    slope = physical.get('slopePercent', model['hydrology']['slopePercent'])
    native_k = physical.get('conductivityMmH', model['hydrology']['conductivityMmH'])
    boundary = physical.get('rainGardenBoundary')
    if boundary is not None and boundary != native_soil_boundary(cell, model['hydrology']):
        raise SimulationQualityError('LIVE_NATIVE_SOIL_BOUNDARY_INVALID')
    bio = physical.get('bioretentionBoundary')
    if bio is not None and bio != bioretention_boundary(cell):
        raise SimulationQualityError('LIVE_BIORETENTION_BOUNDARY_INVALID')
    if any(line.split()[1:2] == ['BC'] for line in source.split('[LID_USAGE]', 1)[1].split('[', 1)[0].splitlines()) and (version != 2 or bio is None):
        raise SimulationQualityError('LIVE_BIORETENTION_BOUNDARY_INVALID')
    rows = []
    for profile in catalog(version)['profiles'].values():
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
        if t == 'BC':
            void_ratio = p['storagePorosity']/(1-p['storagePorosity'])
            rows.append(f'BC STORAGE {p["storageDepthMm"]} {void_ratio} {native_k} 0')
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
    version = model_version(model) if model is not None else 1
    source = catalog(version)
    value = copy.deepcopy({'catalogSha256': design_set(version)['sha256'], 'evidence': source['evidence'],
                          'source': source['source'], 'profile': source['profiles'][facility],
                          'limitations': source['limitations']})
    if facility == 'RAIN_GARDEN' and model is not None:
        boundary = model['cells'][0].get('physicalInputs', {}).get('rainGardenBoundary')
        if boundary is not None:
            value['nativeSoilBoundary'] = copy.deepcopy(boundary)
    if facility == 'BIORETENTION' and model is not None:
        value['nativeSoilBoundary'] = copy.deepcopy(model['cells'][0]['physicalInputs']['bioretentionBoundary'])
    return value
