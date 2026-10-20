"""공개 LID 단면을 기존 집수·관망에 연결하는 불변 설계 입력."""
from collections import defaultdict
from copy import deepcopy
import json
import math
from pathlib import Path
import re

from waterleague_sim.engine.flood_errors import require
from waterleague_sim.engine.swmm import ROOT
from waterleague_sim.ingestion.published_network import digest, records

CATALOG_PATH = ROOT / 'backend/src/main/resources/facilities/epa-connected-designs-v1.json'
CATALOG_SHA256 = 'f06a80aebb4fc674597e1da4ca2f829a58f1724de088d603bf81eb9068e9f0a2'
COMMON = {'id', 'facilityType', 'subcatchmentId', 'areaM2', 'replacedImperviousM2',
          'treatedImperviousM2', 'initialSaturationPercent', 'parameters'}
SEEPAGE_BASES = {'PUBLISHED_MODEL_PARAMETER', 'TEXTURE_CLASS_LITERATURE_ESTIMATE', 'DESIGN_ASSUMPTION'}


def catalog():
    raw = CATALOG_PATH.read_bytes()
    require(digest(raw) == CATALOG_SHA256, 'CONNECTED_FACILITY_CATALOG_CHANGED')
    return json.loads(raw)


def number(value, minimum=0, maximum=1e12, *, positive=False):
    require(type(value) in (int, float) and math.isfinite(value)
            and minimum <= value <= maximum and (not positive or value > 0),
            'CONNECTED_FACILITY_NUMBER_INVALID')
    return value


def identifier(value):
    require(isinstance(value, str) and re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,30}', value),
            'CONNECTED_FACILITY_ID_INVALID')
    return value


def fmt(value):
    return format(value, '.15g')


def indexed(rows):
    result = {}
    for row in rows:
        key = row['tokens'][0].upper()
        require(key not in result, 'CONNECTED_FACILITY_SOURCE_DUPLICATE')
        result[key] = row
    return result


def orifice(drain, area_m2, storage_depth_mm, rain_barrel):
    require(isinstance(drain, dict) and set(drain) == {
        'diameterMm', 'dischargeCoefficient', 'offsetMm', 'delayHours'}, 'CONNECTED_FACILITY_DRAIN_INVALID')
    diameter = number(drain['diameterMm'], maximum=10_000, positive=True) / 1000
    cd = number(drain['dischargeCoefficient'], maximum=1, positive=True)
    offset = number(drain['offsetMm'], maximum=storage_depth_mm)
    require(offset < storage_depth_mm, 'CONNECTED_FACILITY_DRAIN_ABOVE_STORAGE')
    delay = number(drain['delayHours'], maximum=8760)
    require(rain_barrel or delay == 0, 'CONNECTED_FACILITY_DELAY_ONLY_CISTERN')
    opening = math.pi * diameter ** 2 / 4
    require(opening < area_m2, 'CONNECTED_FACILITY_DRAIN_AREA_INVALID')
    # Q=Cd·Ao·sqrt(2gh)를 시설 면적당 mm/h와 mm 수두의 C·h^0.5로 환산한다.
    coefficient = cd * opening / area_m2 * math.sqrt(2 * 9.80665) * 3600 * math.sqrt(1000)
    return coefficient, {'method': 'EPA_VOLUME_III_EQUATION_6_73_SI',
        'gravityMps2': 9.80665, 'openingAreaM2': opening, 'coefficientMmHalfPerHour': coefficient,
        'exponent': .5, 'dischargeCoefficientBasis': 'EXPLICIT_DESIGN_NOT_CALIBRATED',
        'parameters': deepcopy(drain)}


def control(placement, source):
    kind = placement['facilityType']
    require(isinstance(kind, str) and kind in source['profiles'], 'CONNECTED_FACILITY_TYPE_INVALID')
    profile = source['profiles'][kind]
    p = placement['parameters']
    require(isinstance(p, dict), 'CONNECTED_FACILITY_PARAMETERS_INVALID')
    expected = set(profile['ranges'])
    if kind in ('BIORETENTION', 'INFILTRATION_TRENCH'):
        expected |= {'nativeSeepageMmH', 'nativeSeepageBasis', 'drain'}
    if kind == 'RAINWATER_CISTERN':
        expected |= {'storageDepthMm', 'drain'}
    require(set(p) == expected, 'CONNECTED_FACILITY_PARAMETERS_INVALID')
    for key, (low, high) in profile['ranges'].items():
        number(p[key], low, high)
    name = 'WL_' + placement['id']
    area = placement['areaM2']
    rows = [f'{name} {profile["swmmType"]}']
    details = {'source': profile['source'], 'surfaceOutlet': 'EXISTING_CATCHMENT_OUTLET',
               'drainOutlet': 'EXISTING_CATCHMENT_OUTLET', 'initialStateBasis': 'EXPLICIT_DESIGN_SEED'}
    width = 0.
    if kind == 'VEGETATIVE_SWALE':
        require(placement['initialSaturationPercent'] == 0,
                'CONNECTED_FACILITY_SWALE_SATURATION_NOT_APPLICABLE')
        width = p['bottomWidthM'] + 2 * p['surfaceDepthMm'] / 1000 * p['sideSlope']
        details.update({'topWidthM': width, 'lengthM': area / width,
            'infiltrationBasis': 'UNCHANGED_HOST_CATCHMENT_METHOD_AND_PARAMETERS'})
        rows.append(f'{name} SURFACE ' + ' '.join(fmt(v) for v in (
            p['surfaceDepthMm'], p['vegetationFraction'], p['roughness'], p['slopePercent'], p['sideSlope'])))
    elif kind == 'RAINWATER_CISTERN':
        depth = number(p['storageDepthMm'], maximum=100_000, positive=True)
        # RB는 검증 이후 엔진이 공극률 1로 고정하므로 선행 형식 검사용 양수 공극비를 기재한다.
        rows.append(f'{name} STORAGE {fmt(depth)} 1 0 0 YES')
        details.update({'capacityM3': area * depth / 1000, 'covered': True,
                        'effectiveStoragePorosity': 1, 'directRainfall': False, 'reuseCreditedM3': None})
        require(p['drain'] is not None, 'CONNECTED_FACILITY_CISTERN_DRAIN_REQUIRED')
    else:
        native = number(p['nativeSeepageMmH'], maximum=100_000)
        require(isinstance(p['nativeSeepageBasis'], str) and p['nativeSeepageBasis'] in SEEPAGE_BASES,
                'CONNECTED_FACILITY_SEEPAGE_BASIS_REQUIRED')
        vegetation = p['vegetationFraction'] if kind == 'BIORETENTION' else 0
        rows.append(f'{name} SURFACE {fmt(p["surfaceDepthMm"])} {fmt(vegetation)} 0 0 0')
        if kind == 'BIORETENTION':
            s = source['bioretentionSoil']
            rows.append(f'{name} SOIL ' + ' '.join(fmt(v) for v in (p['soilDepthMm'],
                s['porosity'], s['fieldCapacity'], s['wiltingPoint'], s['conductivityMmH'],
                s['conductivitySlope'], s['suctionMm'])))
        porosity = p['storagePorosity']
        rows.append(f'{name} STORAGE {fmt(p["storageDepthMm"])} {fmt(porosity / (1 - porosity))} {fmt(native)} 0')
        details.update({'nativeSeepageMmH': native, 'nativeSeepageBasis': p['nativeSeepageBasis'],
                        'cloggingBasis': 'NEW_UNCLOGGED_DESIGN', 'surfaceOverflow': 'IMMEDIATE_ABOVE_BERM'})
    if p.get('drain') is not None:
        coefficient, evidence = orifice(p['drain'], area, p['storageDepthMm'], kind == 'RAINWATER_CISTERN')
        rows.append(f'{name} DRAIN {fmt(coefficient)} 0.5 {fmt(p["drain"]["offsetMm"])} {fmt(p["drain"]["delayHours"])}')
        details['drain'] = evidence
    return name, width, rows, details


def compile_design(raw, design):
    text, sections = records(raw)
    source = catalog()
    require(isinstance(design, dict) and set(design) == {'schemaVersion', 'basis', 'placements'}
            and type(design['schemaVersion']) is int and design['schemaVersion'] == 1
            and design['basis'] == source['evidence'], 'CONNECTED_FACILITY_DESIGN_INVALID')
    placements = design['placements']
    require(isinstance(placements, list) and 0 < len(placements) <= 256,
            'CONNECTED_FACILITY_PLACEMENTS_INVALID')
    options = {key: row['tokens'][1].upper() for key, row in indexed(sections.get('OPTIONS', [])).items()
               if len(row['tokens']) == 2}
    require(options.get('FLOW_UNITS') == 'CMS' and options.get('FLOW_ROUTING') == 'DYNWAVE',
            'CONNECTED_FACILITY_SI_DYNWAVE_REQUIRED')
    require(not sections.get('LID_USAGE'), 'CONNECTED_FACILITY_UNMODIFIED_BASELINE_REQUIRED')
    catchments = indexed(sections.get('SUBCATCHMENTS', []))
    subareas = indexed(sections.get('SUBAREAS', []))
    nodes = indexed(sections.get('JUNCTIONS', []) + sections.get('STORAGE', []) + sections.get('OUTFALLS', []))
    # 배수 연결이 없는 절점에 시설을 붙여 소실 출구를 만들지 않는다.
    linked = {token.upper() for section in ('CONDUITS', 'PUMPS', 'ORIFICES', 'WEIRS', 'OUTLETS')
              for row in sections.get(section, []) for token in row['tokens'][1:3]}
    groups, names, controls, usages, details = defaultdict(list), set(), [], [], []
    existing_controls = {row['tokens'][0].upper() for row in sections.get('LID_CONTROLS', [])}
    for placement in placements:
        require(isinstance(placement, dict) and set(placement) == COMMON, 'CONNECTED_FACILITY_PLACEMENT_INVALID')
        name = identifier(placement['id']).upper()
        require(name not in names and 'WL_' + name not in existing_controls, 'CONNECTED_FACILITY_ID_DUPLICATED')
        names.add(name)
        catchment = identifier(placement['subcatchmentId']).upper()
        require(catchment in catchments, 'CONNECTED_FACILITY_CATCHMENT_MISSING')
        tokens = catchments[catchment]['tokens']
        require(len(tokens) >= 7 and tokens[2].upper() in nodes and tokens[2].upper() in linked
                and tokens[2].upper() not in catchments,
                'CONNECTED_FACILITY_CONNECTED_OUTLET_REQUIRED')
        require(tokens[2].upper() not in {r['tokens'][0].upper() for r in sections.get('OUTFALLS', [])},
                'CONNECTED_FACILITY_INTERNAL_OUTLET_REQUIRED')
        area = number(placement['areaM2'], positive=True)
        number(placement['replacedImperviousM2'], maximum=area)
        number(placement['treatedImperviousM2'])
        number(placement['initialSaturationPercent'], maximum=100)
        groups[catchment].append(placement)
    lines, changes = text.splitlines(keepends=True), []
    for catchment, items in sorted(groups.items()):
        row = catchments[catchment]
        try:
            area = number(float(row['tokens'][3]), positive=True) * 10_000
            percent = number(float(row['tokens'][4]), maximum=100)
            # 100%의 곱셈 반올림으로 불투수 면적이 원 면적을 넘지 않게 한다.
            impervious = area if percent == 100 else area * percent / 100
        except ValueError:
            require(False, 'CONNECTED_FACILITY_SOURCE_AREA_INVALID')
        used = math.fsum(p['areaM2'] for p in items)
        removed = math.fsum(p['replacedImperviousM2'] for p in items)
        captured = math.fsum(p['treatedImperviousM2'] for p in items)
        remaining = area - used
        available = impervious - removed
        require(remaining > 0 and used - removed <= area - impervious
                and 0 <= available <= remaining, 'CONNECTED_FACILITY_REPLACEMENT_AREA_EXCEEDED')
        # EPA의 99.9% 초과 전면 LID 전환으로 집수 배분 의미가 바뀌는 입력은 별도 모델이 필요하다.
        require(used <= .999 * area, 'CONNECTED_FACILITY_FULL_CATCHMENT_UNSUPPORTED')
        require(captured <= available, 'CONNECTED_FACILITY_CAPTURE_AREA_EXCEEDED')
        if captured:
            require(catchment in subareas and len(subareas[catchment]['tokens']) >= 7
                    and subareas[catchment]['tokens'][6].upper() == 'OUTLET',
                    'CONNECTED_FACILITY_INTERNAL_SUBAREA_ROUTING_UNSUPPORTED')
        new_percent = 100 * available / remaining
        original_line = lines[row['line'] - 1]
        match = re.match(r'(\s*(?:\S+\s+){4})(\S+)', original_line)
        require(match is not None, 'CONNECTED_FACILITY_SOURCE_FORMAT_INVALID')
        lines[row['line'] - 1] = original_line[:match.start(2)] + fmt(new_percent) + original_line[match.end(2):]
        changes.append({'subcatchmentId': row['tokens'][0], 'sourceLine': row['line'],
            'totalAreaM2': area, 'facilityAreaM2': used, 'remainingAreaM2': remaining,
            'replacedImperviousM2': removed, 'remainingImperviousM2': available,
            'capturedImperviousM2': captured, 'originalImperviousPercent': float(row['tokens'][4]),
            'remainingImperviousPercent': new_percent})
        for placement in sorted(items, key=lambda p: p['id'].upper()):
            name, width, rows, detail = control(placement, source)
            controls.extend(rows)
            fraction = 100 * placement['treatedImperviousM2'] / available if available else 0
            usages.append(f'{row["tokens"][0]} {name} 1 {fmt(placement["areaM2"])} {fmt(width)} '
                f'{fmt(placement["initialSaturationPercent"])} {fmt(fraction)} 0 * {row["tokens"][2]} 0')
            details.append({'id': placement['id'], 'swmmId': name, 'subcatchmentId': row['tokens'][0],
                'outletNodeId': row['tokens'][2], 'captureImperviousPercent': fraction, **detail})
    ending = '\r\n' if '\r\n' in text else '\n'
    for section, rows in (('LID_CONTROLS', controls), ('LID_USAGE', usages)):
        markers = [i for i, line in enumerate(lines)
                   if re.fullmatch(r'\s*\[' + section + r'\]\s*(?:;.*)?', line.rstrip('\r\n'), re.I)]
        require(len(markers) <= 1, 'CONNECTED_FACILITY_SOURCE_DUPLICATE')
        if markers:
            lines[markers[0] + 1:markers[0] + 1] = [value + ending for value in rows]
        else:
            if lines and not lines[-1].endswith(('\r', '\n')):
                lines[-1] += ending
            lines.extend([ending, '[' + section + ']' + ending, *[value + ending for value in rows]])
    derived = ''.join(lines).encode()
    return derived, {'schemaVersion': 1, 'classification': source['evidence'],
        'originalSha256': digest(raw), 'derivedSha256': digest(derived),
        'catalogSha256': CATALOG_SHA256, 'compilerSha256': digest(Path(__file__).read_bytes()),
        'design': deepcopy(design), 'source': source['source'], 'catchmentChanges': changes,
        'facilities': details, 'limitations': source['limitations'],
        'rankingEligible': False, 'historicalReconstructionEligible': False}
