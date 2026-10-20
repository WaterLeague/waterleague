"""문헌 수요의 별도 RB 운전 비교. 가용 저류 제한은 원 EPA 엔진에서 계산."""
import hashlib
import json
import math
from pathlib import Path

from .swmm import ROOT, SimulationQualityError

PATH = ROOT / 'backend/src/main/resources/facilities/cistern-demand-v1.json'
SHA256 = '906a613dee765bb00ed476c7a4f5b6d08df2ad7858b6ca4c93a19d10f1bb292e'
IDENTIFIER = 'JKSWE_2018_AREA_EQUIVALENT_UNIFORM_DEMAND_V1'


def catalog():
    try:
        raw = PATH.read_bytes()
        if PATH.is_symlink() or hashlib.sha256(raw).hexdigest() != SHA256:
            raise ValueError()
        return json.loads(raw)
    except (OSError, ValueError):
        raise SimulationQualityError('CISTERN_DEMAND_CATALOG_INVALID') from None


def parameters(identifier, roof_area, tank_area):
    if identifier != IDENTIFIER:
        raise SimulationQualityError('CISTERN_DEMAND_SCENARIO_INVALID')
    if any(type(v) not in (int, float) or not math.isfinite(v) or v <= 0
           for v in (roof_area, tank_area)):
        raise SimulationQualityError('CISTERN_DEMAND_AREA_INVALID')
    spec = catalog()
    daily = spec['referenceDemandM3Day'] * roof_area / spec['referenceRoofAreaM2']
    coefficient = daily / tank_area * 1000 / 24
    if not math.isfinite(coefficient) or not math.isfinite(daily):
        raise SimulationQualityError('CISTERN_DEMAND_AREA_INVALID')
    return {'demandRateM3Day': daily, 'drain': {
        'drainCoefficient': coefficient,
        **{k: spec['withdrawal'][k] for k in ('drainExponent', 'drainOffsetMm', 'drainDelayHours')}}}


def summarize(run, placement, input_sha256):
    from ..spatial.cistern_game import rules
    spec = catalog()
    initial, final = run['initial'], run['final']
    area = placement['areaM2']
    capacity = area * rules()['capacityPerRoofAreaM']
    values = parameters(IDENTIFIER, area, capacity / (rules()['storageDepthMm'] / 1000))
    seconds = final['elapsedSeconds'] - initial['elapsedSeconds']
    demand = values['demandRateM3Day'] * seconds / 86400
    flows = {name: final[field] - initial[field] for name, field in (
        ('inflowM3', 'lidInflowM3'), ('suppliedM3', 'lidDrainageTotalM3'),
        ('overflowM3', 'lidSurfaceRunoffM3'), ('evaporationM3', 'lidEvaporationM3'),
        ('infiltrationM3', 'lidInfiltrationM3'))}
    start_storage, end_storage = initial['lidStorageM3'], final['lidStorageM3']
    residual = (flows['inflowM3'] + start_storage - end_storage - flows['suppliedM3']
                - flows['overflowM3'] - flows['evaporationM3'] - flows['infiltrationM3'])
    if (not all(math.isfinite(v) for v in (*flows.values(), seconds, demand, start_storage, end_storage))
            or seconds <= 0 or min(*flows.values(), start_storage, end_storage) < 0
            or max(start_storage, end_storage) > capacity + 1e-8
            or flows['suppliedM3'] > demand + max(1e-12, demand * 1e-9)
            or abs(residual) > max(1e-8, .01 * (flows['inflowM3'] + start_storage))):
        raise SimulationQualityError('CISTERN_DEMAND_BALANCE_INVALID')
    # 시간 적분의 부동소수 잔차는 원 공급값에 남기고 음의 부족량만 0 경계로 제한한다.
    unmet = max(0, demand - flows['suppliedM3'])
    return {
        'schemaVersion': 1, 'status': 'SUCCEEDED', 'scenarioId': IDENTIFIER,
        'catalogSha256': SHA256, 'inputSha256': input_sha256,
        'classification': spec['classification'], 'source': spec['source'],
        'newerReview': spec['newerReview'], 'limitations': spec['limitations'],
        'rankingEligible': False, 'observedReuseM3': None,
        'roofCollectionAreaM2': area, 'capacityM3': capacity,
        'evaluationStart': initial['at'], 'evaluationEnd': final['at'],
        'evaluationSeconds': seconds, 'demandRateM3Day': values['demandRateM3Day'],
        'drain': values['drain'], 'demandM3': demand, **flows,
        'unmetDemandM3': unmet, 'supplyFraction': min(1, flows['suppliedM3'] / demand),
        'initialStorageM3': start_storage, 'finalStorageM3': end_storage,
        'balanceResidualM3': residual, 'runoffContinuityPercent': run['runoffContinuityPercent'],
        'boundary': spec['withdrawal']['boundary'],
    }


def analyze(model, placement, directory, evaporation, *, evaluation_start_seconds=None):
    from . import continuous, initialization, temporal
    directory = Path(directory)
    run = continuous.replay(model, [placement], directory, 'cistern_demand', evaporation,
        evaluation_start_seconds=evaluation_start_seconds, cistern_scenario=IDENTIFIER)
    if evaluation_start_seconds is not None:
        run = temporal.rebase_activation(run, evaluation_start_seconds)
    elif model.get('initialization') is not None:
        run = initialization.rebase(run, model['initialization']['warmupMinutes'])
    value = summarize(run, placement, continuous.digest((directory / 'cistern_demand.inp').read_bytes()))
    (directory / 'cistern-demand.json').write_bytes(PATH.read_bytes())
    (directory / 'cistern_demand.py').write_bytes(Path(__file__).read_bytes())
    (directory / 'cistern-demand-run.json').write_text(json.dumps(
        {'scenario': value, 'run': run}, ensure_ascii=False, allow_nan=False) + '\n')
    return value
