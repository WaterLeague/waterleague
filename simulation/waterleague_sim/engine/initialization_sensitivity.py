"""같은 평가 창의 선행 기간·건습 시드 민감도 계산. 경쟁 점수 게시 없음."""
import copy
import json
import math
from datetime import datetime, timedelta
from pathlib import Path

from . import continuous, initialization
from .swmm import SimulationQualityError

METHOD = 'OBSERVED_SPINUP_DURATION_SEED_COMPARISON_V1'
METHOD_V2 = 'OBSERVED_SPINUP_FACILITY_STATE_COMPARISON_V2'
FACILITIES = ('RAIN_GARDEN', 'PERMEABLE_PAVEMENT', 'GREEN_ROOF',
              'BIORETENTION', 'INFILTRATION_TRENCH', 'VEGETATIVE_SWALE')
METRICS = {
    'initialSoilMoisture': 'm3/m3', 'initialStorageM3': 'm3', 'initialLidStorageM3': 'm3',
    'initialSurfaceDepthMm': 'mm', 'initialPavementDepthMm': 'mm', 'initialStorageDepthMm': 'mm',
    'evaluatedDischargeM3': 'm3', 'evaluatedEvaporationM3': 'm3',
    'evaluatedInfiltrationM3': 'm3', 'peakDischargeMean1MinM3s': 'm3/s', 'contributionM3': 'm3',
}


def encode(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)+'\n').encode()


def window(antecedent, days):
    if type(days) is not int or days*1440 not in initialization.SUPPORTED_MINUTES:
        raise SimulationQualityError('SPINUP_DURATION_INVALID')
    rain, pet = copy.deepcopy(antecedent['rainfall']), copy.deepcopy(antecedent['evaporation'])
    start, end = [datetime.fromisoformat(rain[k]) for k in ('start', 'end')]
    count = int((end-start).total_seconds()/60)
    minutes = days*1440
    if (start.utcoffset() is None or end.utcoffset() is None or start.second or start.microsecond
            or end.second or end.microsecond or count < minutes
            or count != len(rain['depthsMm']) or count != len(pet['ratesMmDay'])):
        raise SimulationQualityError('SPINUP_SOURCE_PERIOD_INVALID')
    lower = end-timedelta(minutes=minutes)
    rain['start'] = lower.isoformat()
    rain['depthsMm'] = rain['depthsMm'][-minutes:]
    if 'depthMethods' in rain:
        if len(rain['depthMethods']) != count:
            raise SimulationQualityError('SPINUP_SOURCE_PERIOD_INVALID')
        rain['depthMethods'] = rain['depthMethods'][-minutes:]
        rain['reconstructedMinutes'] = sum(v.startswith('OBSERVED_ZERO_') for v in rain['depthMethods'])
    intervals = []
    for interval in rain.get('aggregatedRainIntervals', []):
        a, b = [datetime.fromisoformat(interval[k]) for k in ('start', 'end')]
        a, b = max(a, lower), min(b, end)
        if b <= a:
            continue
        clipped = int((b-a).total_seconds()/60)
        intervals.append(interval | {'start': a.isoformat(), 'end': b.isoformat(), 'minutes': clipped,
                                     'totalMm': interval['totalMm']*clipped/interval['minutes']})
    rain['aggregatedRainIntervals'] = intervals
    rain['qualityWarnings'] = [v for v in rain.get('qualityWarnings', [])
                               if lower <= datetime.fromisoformat(v['at']) <= end]
    pet['ratesMmDay'] = pet['ratesMmDay'][-minutes:]
    # 원문 참조는 긴 원본 창의 해시를 유지하고 실제 사용 구간은 따로 고정한다.
    pet['sourceWindow'] = {'start': lower.isoformat(), 'end': end.isoformat()}
    return {'rainfall': rain, 'evaporation': pet}


def minute_discharge(run):
    previous = run['initial']
    values = []
    for current in run['samples']:
        seconds = current['elapsedSeconds']-previous['elapsedSeconds']
        if abs(seconds-60) > 1e-7:
            raise SimulationQualityError('SPINUP_REPORT_INTERVAL_INVALID')
        values.append((current['surfaceRunoffM3']+current['lidDrainageM3']
                       -previous['surfaceRunoffM3']-previous['lidDrainageM3'])/seconds)
        previous = current
    return values


def measures(base, design):
    first, last = design['initial'], design['final']
    for run in (base, design):
        v = run['final']
        if abs(v['balanceResidualM3']) > max(1e-8, .01*(v['precipitationM3']+v['initialStorageM3'])):
            raise SimulationQualityError('SPINUP_EVALUATION_BALANCE_FAILED')
    return {
        'initialSoilMoisture': first['soilMoisture'], 'initialStorageM3': first['storageM3'],
        'initialLidStorageM3': first['lidStorageM3'], 'initialSurfaceDepthMm': first['surfaceDepthMm'],
        'initialPavementDepthMm': first['pavementDepthMm'], 'initialStorageDepthMm': first['storageDepthMm'],
        'evaluatedDischargeM3': last['surfaceRunoffM3']+last['lidDrainageM3'],
        'evaluatedEvaporationM3': last['evaporationM3'], 'evaluatedInfiltrationM3': last['infiltrationM3'],
        'peakDischargeMean1MinM3s': max(minute_discharge(design)),
        'contributionM3': base['final']['accountedDischargeM3']-last['accountedDischargeM3'],
    }


def compare(cases, days, seeds=(0, 100)):
    expected = {(d, s) for d in days for s in seeds}
    if len(cases) != len(expected) or {(c['days'], c['seedSaturationPercent']) for c in cases} != expected:
        raise SimulationQualityError('SPINUP_COMPARISON_INCOMPATIBLE')
    if any(c['status'] != 'SUCCEEDED' for c in cases):
        return {'status': 'INCOMPLETE', 'ranges': None, 'seedDifferences': None, 'durationDifferences': None}
    def difference(a, b):
        return {key: None if a[key] is None or b[key] is None else b[key]-a[key] for key in METRICS}
    by_key = {(c['days'], c['seedSaturationPercent']): c['metrics'] for c in cases}
    ranges = {}
    for key in METRICS:
        values = [c['metrics'][key] for c in cases]
        if all(v is None for v in values):
            ranges[key] = None
        elif any(v is None or not math.isfinite(v) for v in values):
            raise SimulationQualityError('SPINUP_COMPARISON_INCOMPATIBLE')
        else:
            ranges[key] = {'min': min(values), 'max': max(values), 'span': max(values)-min(values)}
    return {'status': 'MEASURED_NO_UNIVERSAL_CONVERGENCE_THRESHOLD', 'ranges': ranges,
            'seedDifferences': ([{'days': d, 'wetMinusDry': difference(by_key[d, 0], by_key[d, 100])}
                                 for d in days] if seeds == (0, 100) else []),
            'durationDifferences': [{'shortDays': a, 'longDays': b, 'seedSaturationPercent': seed,
                                    'longMinusShort': difference(by_key[a, seed], by_key[b, seed])}
                                   for a, b in zip(days, days[1:]) for seed in seeds]}


def analyze(model, placement, evaporation, antecedent, directory, days=(7, 14), schema_version=1):
    facility = placement.get('facilityType')
    if (not days or tuple(sorted(set(days))) != tuple(days)
            or any(type(d) is not int or d*1440 not in initialization.SUPPORTED_MINUTES for d in days)
            or model.get('initialization') is not None or model.get('facilityDesignSet') is None
            or type(schema_version) is not int or schema_version not in (1, 2)
            or facility not in FACILITIES or (schema_version == 1 and facility == 'VEGETATIVE_SWALE')):
        raise SimulationQualityError('SPINUP_COMPARISON_REQUEST_INVALID')
    seeds = (0,) if facility == 'VEGETATIVE_SWALE' else (0, 100)

    def prepare(prior, duration, seed=0):
        expanded, pet = initialization.prepend(model, evaporation, prior,
                                              warmup_minutes=duration*1440, seed_percent=seed)
        if seeds == (0,):
            # 식생수로에는 포화시킬 토양·저류층이 없으므로 동일 시드를 건습 비교로 표시하지 않는다.
            evidence = expanded['initialization']
            old_limits = evidence['limitations']
            evidence['seed'] = 'EMPTY_SURFACE_DEFAULT_INFILTRATION_STATE'
            evidence['limitations'] = [
                '식생수로는 빈 표면·엔진 기본 침투 상태로 시작하며 LID 초기 포화도 비교 대상이 아님',
                '원지반 침투 매개변수를 바꾸어 건습 상태 비교로 대체하지 않음',
            ] + old_limits[1:]
            expanded['assumptions'] = [v for v in expanded['assumptions'] if v not in old_limits]
            expanded['assumptions'] += evidence['limitations']
        return expanded, pet
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    if any(directory.iterdir()):
        raise SimulationQualityError('SPINUP_OUTPUT_ALREADY_EXISTS')
    request = dict(model=model, placement=placement, evaporation=evaporation, antecedent=antecedent, days=days)
    if schema_version == 2:
        request['schema_version'] = schema_version
    (directory/'input.json').write_bytes(encode(request))
    cases = []
    for duration in days:
        prior = window(antecedent, duration)
        base_model, pet = prepare(prior, duration)
        try:
            baseline = continuous.replay(base_model, [], directory, f'baseline_{duration}d', pet)
        except SimulationQualityError as error:
            cases.extend({'days': duration, 'seedSaturationPercent': seed, 'status': 'FAILED',
                          'phase': 'BASELINE', 'errorCode': str(error)} for seed in seeds)
            continue
        for seed in seeds:
            label = f'design_{duration}d_{seed}'
            expanded, pet = prepare(prior, duration, seed)
            case = {'days': duration, 'seedSaturationPercent': seed, 'label': label}
            try:
                replay = continuous.replay(expanded, [placement], directory, label, pet)
                base, design, evidence = initialization.evaluation_window(expanded, baseline, replay)
                case.update(status='SUCCEEDED', metrics=measures(base, design), initialization=evidence,
                            runoffContinuityPercent=design['runoffContinuityPercent'],
                            evaluationBalanceResidualM3=design['final']['balanceResidualM3'])
                trace = [{'at': a['at'], 'baselineMean1MinM3s': qa, 'strategyMean1MinM3s': qb,
                          'soilMoisture': b['soilMoisture'], 'storageM3': b['storageM3'],
                          'contributionM3': a['accountedDischargeM3']-b['accountedDischargeM3']}
                         for a, b, qa, qb in zip(base['samples'], design['samples'],
                                                minute_discharge(base), minute_discharge(design), strict=True)]
                (directory/(label+'.json')).write_bytes(encode({'initial': design['initial'], 'final': design['final'], 'samples': trace}))
            except SimulationQualityError as error:
                case.update(status='FAILED', errorCode=str(error))
            cases.append(case)
    report = {'schemaVersion': schema_version, 'method': METHOD if schema_version == 1 else METHOD_V2,
              'scope': 'INPUT_BOUND_INDEPENDENT_SURFACE_ONLY',
              'inputSha256': continuous.digest(encode(request)), 'cellId': placement['cellId'],
              'facilityType': placement['facilityType'], 'areaM2': placement['areaM2'],
              'evaluationStart': model['rainfall']['start'], 'evaluationEnd': model['rainfall']['end'],
              'stationId': model['rainfall']['stationId'], 'units': METRICS, 'cases': cases,
              'comparison': compare(cases, days, seeds), 'engine': continuous.engine_identity(),
              'limitations': [('건습 시드는 관측 수분이 아닌 초기 상태 경계 시나리오' if len(seeds) == 2
                               else '식생수로의 단일 시작 상태이며 건습 시드 수렴을 검증하지 않음'),
                              '선택 입력에서의 민감도이며 서울 전역 수렴·현장 정확도 검증 아님',
                              '관망 없는 독립 표면의 유출·배수 합계 1분 평균 첨두이며 하류 침수 첨두 아님',
                              '경쟁 기록·점수·기존 초기화 정책 변경 없음']}
    if schema_version == 2:
        report['seedPolicy'] = ('LID_SATURATION_BOUNDARIES' if len(seeds) == 2
                                else 'NOT_APPLICABLE_FIXED_EMPTY_SURFACE')
    (directory/'sensitivity.json').write_bytes(encode(report))
    for name in ('continuous.py', 'swmm.py', 'initialization.py', 'initialization_sensitivity.py', 'facilities.py', 'runoff_metrics.py'):
        (directory/name).write_bytes((Path(__file__).parent/name).read_bytes())
    (directory/'site_geometry.py').write_bytes((continuous.ROOT/'simulation/waterleague_sim/spatial/geometry.py').read_bytes())
    from .facilities import source_path
    (directory/'facility-designs.json').write_bytes(source_path(model).read_bytes())
    (directory/'lid_snapshot.inc').write_bytes((continuous.ROOT/'simulation/native/lid_snapshot.inc').read_bytes())
    (directory/'manifest.json').write_bytes(encode({p.name: continuous.digest(p.read_bytes())
        for p in sorted(directory.iterdir()) if p.is_file()}))
    return report
