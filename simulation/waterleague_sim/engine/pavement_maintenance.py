"""공개 블록 막힘 시험의 고정 투수 조건 비교. 현장 노후화·청소 효과 추정 없음."""
import copy
import hashlib
import importlib.metadata
import json
import platform
from decimal import Decimal
from pathlib import Path

from .swmm import ROOT, SimulationQualityError

CATALOG_PATH = ROOT/'backend/src/main/resources/facilities/pavement-maintenance-v1.json'
CATALOG_SHA256 = 'a9166ec93e6a6af4c460028f438c33fc67af0a1675502491e04f248c8e7dfd88'
METHOD = 'FIXED_PERMEABILITY_MATERIAL_COMPARISON_V1'


def encode(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)+'\n').encode()


def catalog():
    try:
        if CATALOG_PATH.is_symlink():
            raise ValueError()
        raw = CATALOG_PATH.read_bytes()
        if hashlib.sha256(raw).hexdigest() != CATALOG_SHA256:
            raise ValueError()
        return json.loads(raw)
    except (OSError, ValueError):
        raise SimulationQualityError('PAVEMENT_COMPARISON_CATALOG_INVALID') from None


def scenario(identifier):
    source = catalog()
    selected = next((v for v in source['cases'] if v['id'] == identifier), None)
    if selected is None:
        raise SimulationQualityError('PAVEMENT_COMPARISON_SCENARIO_INVALID')
    row = source['rawRows'][selected['row']]
    # 원문의 mm/s를 mm/h로 환산하며 관측 비율로 유출량을 직접 배율 조정하지 않는다.
    conductivity = float(Decimal(str(row['permeabilityMmS']))*3600)
    return {
        **selected, **row, 'catalogId': source['id'], 'catalogSha256': CATALOG_SHA256,
        'pavementDepthMm': source['specimen']['depthMm'],
        'pavementPorosity': source['specimen']['initialPorosity'],
        'conductivityMmH': conductivity, 'imperviousFraction': 0, 'cloggingFactor': 0,
        'timePolicy': 'FIXED_THROUGH_SPINUP_AND_EVENT_NO_AUTOMATIC_AGING_OR_CLEANING',
    }


def validate_request(model, placements):
    from .facilities import model_version
    if (model_version(model) != 4 or len(placements) != 1
            or placements[0].get('facilityType') != 'PERMEABLE_PAVEMENT'
            or model.get('sharedSiteSource', {}).get('inflowPolicy') != 'DIRECT_RAINFALL_ONLY'):
        raise SimulationQualityError('PAVEMENT_COMPARISON_REQUEST_INVALID')


def apply(source, model, placements, identifier):
    validate_request(model, placements)
    value = scenario(identifier)
    lines, count, section = [], 0, ''
    for line in source.splitlines():
        if line.startswith('['):
            section = line
        if section == '[LID_CONTROLS]' and line.split()[:2] == ['PP', 'PAVEMENT']:
            porosity = value['pavementPorosity']
            line = (f'PP PAVEMENT {value["pavementDepthMm"]} {porosity/(1-porosity)} '
                    f'0 {value["conductivityMmH"]} 0')
            count += 1
        lines.append(line)
    if count != 1:
        raise SimulationQualityError('PAVEMENT_COMPARISON_INPUT_INVALID')
    return '\n'.join(lines)+'\n'


def analyze(model, placement, evaporation, antecedent, directory):
    from . import continuous, initialization
    from .initialization_sensitivity import measures, METRICS
    from ..evaluation.score_policy import verified_policy
    validate_request(model, [placement])
    if model.get('initialization') is not None:
        raise SimulationQualityError('PAVEMENT_COMPARISON_REQUEST_INVALID')
    source = catalog()
    policy_raw, _ = verified_policy()
    policy_sha256 = continuous.digest(policy_raw)
    request = copy.deepcopy(dict(
        model=model, placement=placement, evaporation=evaporation, antecedent=antecedent,
        catalogSha256=CATALOG_SHA256, sourcePolicySha256=policy_sha256, method=METHOD))
    expanded, pet = initialization.prepend(
        request['model'], request['evaporation'], request['antecedent'])
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    if any(directory.iterdir()):
        raise SimulationQualityError('PAVEMENT_COMPARISON_OUTPUT_EXISTS')
    (directory/'input.json').write_bytes(encode(request))
    baseline, baseline_error = None, None
    try:
        baseline = continuous.replay(expanded, [], directory, 'baseline', pet)
    except SimulationQualityError as error:
        baseline_error = str(error)
    cases = []
    for selected in source['cases']:
        identifier = selected['id']
        case = {'scenario': scenario(identifier)}
        if baseline_error is not None:
            case.update(status='FAILED', phase='BASELINE', errorCode=baseline_error)
        else:
            try:
                design = continuous.replay(
                    expanded, [request['placement']], directory, identifier, pet,
                    pavement_scenario=identifier)
                base, evaluated, evidence = initialization.evaluation_window(
                    expanded, baseline, design)
                case.update(
                    status='SUCCEEDED', metrics=measures(base, evaluated),
                    initialization=evidence,
                    runoffContinuityPercent=design['runoffContinuityPercent'],
                    evaluationBalanceResidualM3=evaluated['final']['balanceResidualM3'],
                    inputSha256=continuous.digest((directory/(identifier+'.inp')).read_bytes()))
                (directory/(identifier+'.json')).write_bytes(encode({
                    'initial': evaluated['initial'], 'final': evaluated['final'],
                    'samples': evaluated['samples'], 'runoffMetrics': design['runoffMetrics'],
                    'scenario': design['pavementScenario']}))
            except SimulationQualityError as error:
                case.update(status='FAILED', phase='SCENARIO', errorCode=str(error))
        cases.append(case)
    complete = all(c['status'] == 'SUCCEEDED' for c in cases)
    differences = None
    if complete:
        fresh = cases[0]['metrics']
        differences = [{
            'scenarioId': c['scenario']['id'],
            'minusFresh': {k: None if c['metrics'][k] is None or fresh[k] is None
                           else c['metrics'][k]-fresh[k] for k in METRICS},
        } for c in cases[1:]]
    report = {
        'schemaVersion': 1, 'method': METHOD, 'scope': source['scope'],
        'status': 'SUCCEEDED' if complete else 'INCOMPLETE',
        'inputSha256': continuous.digest(encode(request)),
        'sourcePolicySha256': policy_sha256,
        'catalogSha256': CATALOG_SHA256, 'source': source['source'],
        'specimen': source['specimen'], 'cellId': placement['cellId'],
        'areaM2': placement['areaM2'], 'facilityType': 'PERMEABLE_PAVEMENT',
        'evaluationStart': model['rainfall']['start'], 'evaluationEnd': model['rainfall']['end'],
        'stationId': model['rainfall']['stationId'], 'units': METRICS,
        'cases': cases, 'differencesFromFresh': differences, 'rankingEligible': False,
        'cleaningRecovery': source['cleaningRecovery'], 'engine': continuous.engine_identity(),
        'runtime': {
            'python': platform.python_version(), 'system': platform.system(),
            'machine': platform.machine(),
            'packages': {name: importlib.metadata.version(name) for name in ('pyproj', 'shapely')},
        },
        'limitations': source['fixedAssumptions'] + [
            '기존 설치의 재료·비용·결과·순위는 변경하지 않는 별도 문헌 재료 비교',
            '새 블록과 협잡물 조건의 차이이며 실제 사용 연수·관리 지연 기간의 예측 아님',
            '현장 설치 인증·완성 포장체의 열화·청소 효과 검증 아님'],
    }
    # 실행 도중 카탈로그 교체도 성공 결과로 게시하지 않는다.
    catalog()
    if verified_policy()[0] != policy_raw:
        raise SimulationQualityError('PAVEMENT_COMPARISON_SOURCE_CHANGED')
    (directory/'comparison.json').write_bytes(encode(report))
    (directory/'source-policy.json').write_bytes(policy_raw)
    (directory/'pavement-maintenance.json').write_bytes(CATALOG_PATH.read_bytes())
    from .facilities import source_path
    (directory/'facility-designs.json').write_bytes(source_path(model).read_bytes())
    for filename in ('reference-surfaces-v1.json', 'site-suitability-v1.json'):
        (directory/filename).write_bytes((CATALOG_PATH.parent/filename).read_bytes())
    package = ROOT/'simulation/waterleague_sim'
    for path in sorted(package.rglob('*.py')):
        target = directory/'code'/path.relative_to(package)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(path.read_bytes())
    (directory/'lid_snapshot.inc').write_bytes((ROOT/'simulation/native/lid_snapshot.inc').read_bytes())
    for filename in ('pyproject.toml', 'uv.lock'):
        (directory/filename).write_bytes((ROOT/'simulation'/filename).read_bytes())
    (directory/'manifest.json').write_bytes(encode({
        str(p.relative_to(directory)): continuous.digest(p.read_bytes())
        for p in sorted(directory.rglob('*')) if p.is_file()}))
    return report
