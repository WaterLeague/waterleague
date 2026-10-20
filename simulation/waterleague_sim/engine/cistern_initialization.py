"""동일 관측 창의 이용조 초기 저류 경계와 운전 조건별 비교."""
import math
from pathlib import Path

from . import cistern_demand, continuous, initialization
from .initialization_sensitivity import compare, encode, measures, window, METRICS
from .swmm import SimulationQualityError
from ..spatial import cistern_game

METHOD = 'OBSERVED_CISTERN_STORAGE_DEMAND_COMPARISON_V3'
OPERATIONS = ('NATURAL_DRAIN', 'LITERATURE_DEMAND')


def prepare(model, evaporation, antecedent, days, seed):
    expanded, pet = initialization.prepend(model, evaporation, antecedent,
        warmup_minutes=days * 1440, seed_percent=seed)
    evidence = expanded['initialization']
    previous = evidence['limitations']
    evidence['seed'] = 'EMPTY_CISTERN' if seed == 0 else 'FULL_CISTERN'
    evidence['limitations'] = [
        f'선행 {days}일 이전 실측 저류 미확보로 ' + ('빈 이용조' if seed == 0 else '가득 찬 이용조') + '에서 시작',
        '토양 포화도가 아닌 이용조 초기 저류의 경계 조건이며 현장 관측값 아님',
    ] + previous[1:]
    expanded['assumptions'] = [s for s in expanded['assumptions'] if s not in previous] + evidence['limitations']
    return expanded, pet


def tank_state(run, capacity):
    first, last = run['initial'], run['final']
    result = {'initialStorageM3': first['lidStorageM3'], 'finalStorageM3': last['lidStorageM3']}
    result.update({name: last[key] - first[key] for name, key in (
        ('inflowM3', 'lidInflowM3'), ('outflowM3', 'lidDrainageTotalM3'),
        ('overflowM3', 'lidSurfaceRunoffM3'), ('evaporationM3', 'lidEvaporationM3'),
        ('infiltrationM3', 'lidInfiltrationM3'))})
    if (any(not math.isfinite(v) or v < 0 for v in result.values())
            or max(result['initialStorageM3'], result['finalStorageM3']) > capacity + 1e-8):
        raise SimulationQualityError('CISTERN_SPINUP_TANK_STATE_INVALID')
    result['balanceResidualM3'] = (result['inflowM3'] + result['initialStorageM3']
        - result['finalStorageM3'] - result['outflowM3'] - result['overflowM3']
        - result['evaporationM3'] - result['infiltrationM3'])
    if abs(result['balanceResidualM3']) > max(1e-8, .01 * (result['inflowM3'] + result['initialStorageM3'])):
        raise SimulationQualityError('CISTERN_SPINUP_TANK_BALANCE_FAILED')
    return result


def analyze(model, placement, evaporation, antecedent, directory, days=(7,), schema_version=3):
    if (schema_version != 3 or type(schema_version) is not int
            or placement.get('facilityType') != cistern_game.TYPE
            or model.get('facilityDesignSet') != cistern_game.rules()['facilityDesignSet']
            or model.get('initialization') is not None or not days
            or tuple(sorted(set(days))) != tuple(days)
            or any(type(d) is not int or d * 1440 not in initialization.SUPPORTED_MINUTES for d in days)):
        raise SimulationQualityError('CISTERN_SPINUP_REQUEST_INVALID')
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    if any(directory.iterdir()):
        raise SimulationQualityError('SPINUP_OUTPUT_ALREADY_EXISTS')
    capacity = placement['areaM2'] * cistern_game.rules()['capacityPerRoofAreaM']
    request = {'model': model, 'placement': placement, 'evaporation': evaporation,
        'antecedent': antecedent, 'days': days, 'schema_version': 3,
        'rulesSha256': cistern_game.SHA256, 'demandCatalogSha256': cistern_demand.SHA256}
    (directory / 'input.json').write_bytes(encode(request))
    cases = []
    for duration in days:
        prior = window(antecedent, duration)
        base_model, pet = prepare(model, evaporation, prior, duration, 0)
        baseline, baseline_error = None, None
        try:
            baseline = continuous.replay(base_model, [], directory, f'baseline_{duration}d', pet)
        except SimulationQualityError as error:
            baseline_error = str(error)
        for operation in OPERATIONS:
            scenario = cistern_demand.IDENTIFIER if operation == 'LITERATURE_DEMAND' else None
            for seed in (0, 100):
                label = f'{operation.lower()}_{duration}d_{seed}'
                case = {'days': duration, 'seedSaturationPercent': seed, 'operation': operation, 'label': label}
                if baseline_error is not None:
                    cases.append(case | {'status': 'FAILED', 'phase': 'BASELINE', 'errorCode': baseline_error})
                    continue
                expanded, pet = prepare(model, evaporation, prior, duration, seed)
                try:
                    native = continuous.replay(expanded, [placement], directory, label, pet,
                        cistern_scenario=scenario)
                    seed_storage = native['initial']['lidStorageM3']
                    if not math.isclose(seed_storage, capacity * seed / 100, rel_tol=1e-10, abs_tol=1e-8):
                        raise SimulationQualityError('CISTERN_SPINUP_SEED_NOT_APPLIED')
                    base, design, evidence = initialization.evaluation_window(expanded, baseline, native)
                    input_hash = continuous.digest((directory / (label + '.inp')).read_bytes())
                    demand = cistern_demand.summarize(design, placement, input_hash) if scenario else None
                    case.update(status='SUCCEEDED', inputSha256=input_hash,
                        nativeSeedStorageM3=seed_storage, preparationStart=native['initial']['at'],
                        metrics=measures(base, design), tank=tank_state(design, capacity),
                        initialization=evidence, demand=demand,
                        runoffContinuityPercent=design['runoffContinuityPercent'],
                        evaluationBalanceResidualM3=design['final']['balanceResidualM3'])
                    (directory / (label + '.json')).write_bytes(encode({
                        'case': case, 'nativeInitial': native['initial'], 'initial': design['initial'],
                        'final': design['final'], 'samples': design['samples']}))
                except SimulationQualityError as error:
                    case.update(status='FAILED', errorCode=str(error))
                cases.append(case)
    comparisons = [{'operation': operation, 'comparison': compare(
        [c for c in cases if c['operation'] == operation], days)} for operation in OPERATIONS]
    complete = all(c['status'] == 'SUCCEEDED' for c in cases)
    report = {'schemaVersion': 3, 'method': METHOD, 'scope': 'INPUT_BOUND_INDEPENDENT_SURFACE_ONLY',
        'seedPolicy': 'CISTERN_EMPTY_FULL_STORAGE_BOUNDARIES', 'rankingEligible': False,
        'inputSha256': continuous.digest(encode(request)), 'cellId': placement['cellId'],
        'facilityType': cistern_game.TYPE, 'areaM2': placement['areaM2'], 'capacityM3': capacity,
        'evaluationStart': model['rainfall']['start'], 'evaluationEnd': model['rainfall']['end'],
        'stationId': model['rainfall']['stationId'], 'rulesSha256': cistern_game.SHA256,
        'demandCatalogSha256': cistern_demand.SHA256, 'cases': cases, 'units': METRICS,
        'status': 'SUCCEEDED' if complete else 'INCOMPLETE', 'comparisons': comparisons,
        'engine': continuous.engine_identity(),
        'seedEvidence': {'method': 'EPA_SWMM_5_2_4_LID_INIT_STATE',
            'url': 'https://raw.githubusercontent.com/USEPA/Stormwater-Management-Model/v5.2.4/src/solver/lid.c',
            'reference': 'lid_initState: storageDepth = initSat * storage.thickness'},
        'limitations': [
            '빈 상태·가득 찬 상태는 선행 계산 시작 조건이며 관측 저류량 아님',
            '같은 선행 강우·기상을 연속 계산한 사건 시작 상태를 비교하며 사건 직전 저류 초기화 없음',
            '자연배수와 문헌 수요 인출은 별도 운전 조건이며 각각의 초기 저류 차이만 비교',
            '수요 운전의 경계 배출에는 잠재 인출량이 포함되며 유역의 영구 유출 저감량 아님',
            '수요는 문헌의 면적 비례·일중 균등 가정이며 실제 재이용·수질·하수 환류 미확인',
            '일부 조건 실패는 0으로 대체하지 않으며 해당 운전 비교의 범위·차이를 보류',
            '조건 간 차이는 확률 신뢰구간·초기 상태의 전역 수렴·현장 정확도 인증이 아님',
            '일반 설계 결과·예산·순위에 비교값 합산 없음']}
    (directory / 'sensitivity.json').write_bytes(encode(report))
    for name in ('cistern_initialization.py', 'cistern_game.py', 'cistern_demand.py', 'continuous.py',
                 'swmm.py', 'initialization.py', 'initialization_sensitivity.py', 'facilities.py', 'runoff_metrics.py'):
        (directory / name).write_bytes(Path(__file__).with_name(name).read_bytes())
    (directory / 'cistern_game_catalog.py').write_bytes(Path(cistern_game.__file__).read_bytes())
    (directory / 'cistern-game.json').write_bytes(cistern_game.PATH.read_bytes())
    (directory / 'cistern-demand.json').write_bytes(cistern_demand.PATH.read_bytes())
    from .facilities import source_path
    (directory / 'facility-designs.json').write_bytes(source_path(model).read_bytes())
    for name in ('geometry.py', 'reference_conditions.py', 'design_footprint.py'):
        (directory / name).write_bytes((continuous.ROOT / 'simulation/waterleague_sim/spatial' / name).read_bytes())
    (directory / 'reference-surfaces.json').write_bytes((continuous.ROOT / 'backend/src/main/resources/facilities/reference-surfaces-v1.json').read_bytes())
    (directory / 'lid_snapshot.inc').write_bytes((continuous.ROOT / 'simulation/native/lid_snapshot.inc').read_bytes())
    (directory / 'manifest.json').write_bytes(encode({p.name: continuous.digest(p.read_bytes())
        for p in sorted(directory.iterdir()) if p.is_file()}))
    return report
