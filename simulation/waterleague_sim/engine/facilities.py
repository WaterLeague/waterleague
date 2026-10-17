"""공개 문헌의 설계 제원과 SWMM 입력 단위 연결."""
import copy
import hashlib
import json
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


def apply(source, model):
    if model.get('facilityDesignSet') != design_set():
        raise SimulationQualityError('LIVE_FACILITY_DESIGN_INVALID')
    cell = model['cells'][0]
    physical = cell.get('physicalInputs', {})
    slope = physical.get('slopePercent', model['hydrology']['slopePercent'])
    native_k = physical.get('conductivityMmH', model['hydrology']['conductivityMmH'])
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


def evidence(facility):
    source = catalog()
    return copy.deepcopy({'catalogSha256': CATALOG_SHA256, 'evidence': source['evidence'],
                          'source': source['source'], 'profile': source['profiles'][facility],
                          'limitations': source['limitations']})
