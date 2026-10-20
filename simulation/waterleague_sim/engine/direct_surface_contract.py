"""현재 원형 표면 설계의 공간·입력·평가·비용 근거를 같은 산출물에 결속."""
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re


VERSION = 'NATIVE_DIRECT_SURFACE_COMPARISON_V1'


class DirectSurfaceContractError(ValueError):
    def __init__(self):
        super().__init__('LIVE_COMPARISON_CONTRACT_INVALID')


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def section(raw, name):
    active, rows = False, []
    for line in raw.decode('utf-8').splitlines():
        text = line.strip()
        if text.startswith('['):
            if active:
                break
            active = text == '[' + name + ']'
        elif active and text and not text.startswith(';'):
            rows.append(text)
    if not rows:
        raise DirectSurfaceContractError()
    return '\n'.join(rows).encode('utf-8')


def build(model, placement, result, directory, cost_record):
    try:
        directory = Path(directory)
        cell, = model['cells']
        geometry, link = model['geometrySource'], model['sharedSiteSource']
        area = placement['areaM2']
        if (cell['id'] != placement['cellId'] or placement['facilityType'] not in cell['allowedTypes']
                or type(area) not in (int, float) or not math.isfinite(area) or not 0 < area <= cell['maxAreaM2']
                or geometry['coordinateSystem'] != 'EPSG:5186' or cell['geometryCrs'] != 'EPSG:5186'
                or geometry['geometrySha256'] != cell['geometrySha256']
                or geometry['sourceObjectId'] != cell['sourceObjectId']
                or geometry['playCatalogSha256'] != link['siteCatalogHash']
                or cell['districtId'] != link['districtId']
                or link['inflowPolicy'] != 'DIRECT_RAINFALL_ONLY'):
            raise DirectSurfaceContractError()
        for key in ('playCatalogSha256', 'sitesSha256', 'objectsSha256', 'geometrySha256'):
            if not re.fullmatch('[a-f0-9]{64}', geometry[key]):
                raise DirectSurfaceContractError()
        baseline, strategy = result['baseline'], result['strategy']
        first, last = baseline['initial']['at'], baseline['final']['at']
        if (first != strategy['initial']['at'] or last != strategy['final']['at']
                or baseline['engine'] != strategy['engine']
                or any(run['routingStatus'] != 'NOT_APPLICABLE_NO_CONVEYANCE_NETWORK'
                       or run['runoffMetrics']['start'] != first or run['runoffMetrics']['end'] != last
                       or run['runoffMetrics']['maximumStepSeconds'] != 1 for run in (baseline, strategy))):
            raise DirectSurfaceContractError()
        utc = []
        for value in (first, last):
            at = datetime.fromisoformat(value)
            if at.utcoffset() is None:
                raise DirectSurfaceContractError()
            utc.append(at.astimezone(timezone.utc))
        if utc[0] >= utc[1]:
            raise DirectSurfaceContractError()
        # 기준안과 설계안의 시계·강우·증발·수치 정책이 실제 INP에서도 같아야 한다.
        common = {}
        a, b = (directory / 'baseline.inp').read_bytes(), (directory / 'strategy.inp').read_bytes()
        for name in ('OPTIONS', 'RAINGAGES', 'EVAPORATION', 'TIMESERIES'):
            one, two = section(a, name), section(b, name)
            if one != two:
                raise DirectSurfaceContractError()
            common[name] = digest(one)
        if not any(line.split() == ['FLOW_UNITS', 'CMS'] for line in section(a, 'OPTIONS').decode().splitlines()):
            raise DirectSurfaceContractError()
        source_hashes = {name: digest((directory / name).read_bytes())
                         for name in ('model.json', 'placement.json', 'baseline.inp', 'strategy.inp')}
        if (json.loads((directory / 'model.json').read_bytes()) != model
                or json.loads((directory / 'placement.json').read_bytes()) != placement):
            raise DirectSurfaceContractError()
        if cost_record['status'] == 'RECORDED':
            if digest((directory / 'cost-snapshot.json').read_bytes()) != cost_record['sha256']:
                raise DirectSurfaceContractError()
        elif cost_record != {'status': 'NOT_RECORDED', 'sha256': None, 'estimate': None}:
            raise DirectSurfaceContractError()
        life_cycle = result.get('lifeCycleCost')
        life_cycle_binding = None
        if life_cycle is not None:
            raw = (directory / 'life-cycle-cost.json').read_bytes()
            if (json.loads(raw) != life_cycle
                    or life_cycle['status'] not in ('UNAVAILABLE', 'PARTIAL', 'COMPLETE')
                    or digest((directory / 'life-cycle-cost-plan.json').read_bytes()) != life_cycle['planSha256']
                    or digest((directory / 'life-cycle-method.json').read_bytes()) != life_cycle['policySha256']):
                raise DirectSurfaceContractError()
            life_cycle_binding = {'reportSha256': digest(raw), 'planSha256': life_cycle['planSha256'],
                                  'policySha256': life_cycle['policySha256']}
        return {
            'version': VERSION,
            'spatial': dict(geometry, candidateId=cell['id'], districtId=cell['districtId'],
                            evaluationSurfaceAreaM2=cell['areaM2']),
            'facility': {'type': placement['facilityType'], 'areaM2': area,
                         'designSet': model['facilityDesignSet'], 'referenceScenario': model['referenceScenario']},
            'connection': {'inflowPolicy': 'DIRECT_RAINFALL_ONLY', 'directRainAreaM2': area,
                           'externalCatchment': None, 'drainageNode': None, 'network': None,
                           'status': 'UNCONNECTED_SURFACE_EXPLORATION'},
            'evaluation': {'start': utc[0].isoformat(), 'end': utc[1].isoformat(), 'timeZone': 'UTC',
                           'scope': 'SELECTED_SURFACE_OUTLET_NOT_SEWER_OR_RIVER',
                           'runoffStepSeconds': 1, 'scoreRule': result['scoreRule'],
                           'initialization': result.get('initialization'),
                           'windowMethod': 'INSTALLATION_OFFSET_AFTER_ANTECEDENT' if 'installedAt' in result
                                           else 'FULL_EVENT_AFTER_ANTECEDENT'},
            'units': {'coordinate': 'm', 'area': 'm2', 'volume': 'm3', 'flow': 'm3/s',
                      'rainfall': 'mm', 'cost': 'KRW'},
            'cost': {'status': cost_record['status'], 'snapshotSha256': cost_record['sha256'],
                     'sourceSha256': model['costSourceSha256'], 'budgetPolicy': model['budgetPolicy'],
                     'completeInstalledCostStatus': 'UNCONFIRMED',
                     'lifeCycleCostStatus': life_cycle['status'] if life_cycle is not None else 'NOT_CALCULATED',
                     'lifeCycleCost': life_cycle_binding},
            'engine': baseline['engine'], 'inputFiles': source_hashes, 'commonInpSections': common,
            'implementationSha256': digest(Path(__file__).read_bytes()),
        }
    except (KeyError, TypeError, ValueError, OSError, ArithmeticError):
        raise DirectSurfaceContractError() from None


def archive(model, placement, result, directory, cost_record):
    from .flow_connections import direct_surface, archive as archive_flow
    directory = Path(directory)
    value = build(model, placement, result, directory, cost_record)
    value['flowGraph'] = direct_surface(model, placement, result, value['inputFiles'])
    archive_flow(value['flowGraph'], directory)
    raw = (json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False) + '\n').encode('utf-8')
    result['designContract'] = {'sha256': digest(raw), **value}
    (directory / 'design-contract.json').write_bytes(raw)
    (directory / 'direct_surface_contract.py').write_bytes(Path(__file__).read_bytes())
    (directory / 'result.json').write_text(json.dumps(result, ensure_ascii=False, allow_nan=False) + '\n')
    (directory / 'manifest.json').write_text(json.dumps({p.name: digest(p.read_bytes())
        for p in sorted(directory.iterdir()) if p.is_file() and p.name != 'manifest.json'}, indent=2) + '\n')
    return result['designContract']
