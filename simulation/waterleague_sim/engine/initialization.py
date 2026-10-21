"""선행 관측 재생의 종료 상태를 평가 시작 상태로 전달하고 점수 구간 분리."""
import copy
from datetime import datetime, timedelta
from .swmm import SimulationQualityError

METHOD = 'OBSERVED_7_DAY_CONTINUOUS_SPINUP_V1'
SENSITIVITY_METHOD = 'OBSERVED_DURATION_SEED_SPINUP_V1'
MINUTES = 7*24*60
SUPPORTED_MINUTES = (MINUTES, 14*24*60, 28*24*60)
CUMULATIVE = ('precipitationM3', 'evaporationM3', 'infiltrationM3', 'surfaceRunoffM3',
              'lidDrainageM3', 'lidInflowM3', 'lidEvaporationM3', 'lidInfiltrationM3',
              'lidSurfaceRunoffM3', 'lidDrainageTotalM3')


def prepend(model, evaporation, antecedent, *, warmup_minutes=MINUTES, seed_percent=0):
    if (type(warmup_minutes) is not int or warmup_minutes not in SUPPORTED_MINUTES
            or type(seed_percent) is not int or seed_percent not in (0, 100)):
        raise SimulationQualityError('LIVE_ANTECEDENT_POLICY_INVALID')
    rain = model['rainfall']
    start = datetime.fromisoformat(rain['start'])
    prior = antecedent['rainfall']
    pet = antecedent['evaporation']
    if (datetime.fromisoformat(prior['end']) != start
            or datetime.fromisoformat(prior['start']) != start-timedelta(minutes=warmup_minutes)
            or prior['intervalSeconds'] != 60 or len(prior['depthsMm']) != warmup_minutes
            or len(pet['ratesMmDay']) != warmup_minutes
            or not prior.get('sourceHashes') or not pet.get('sourceHashes')
            or prior['stationId'] != rain['stationId']):
        raise SimulationQualityError('LIVE_ANTECEDENT_BINDING_INVALID')
    value = copy.deepcopy(model)
    value['rainfall'] = rain | {'start': prior['start'], 'depthsMm': prior['depthsMm']+rain['depthsMm'],
        'sourceHashes': sorted(set(prior['sourceHashes']+rain.get('sourceHashes', [rain.get('sourceHash')])) - {None})}
    legacy = warmup_minutes == MINUTES and seed_percent == 0
    value['initialization'] = {'method': METHOD if legacy else SENSITIVITY_METHOD, 'evaluationStart': start.isoformat(),
        'warmupMinutes': warmup_minutes, 'evidence': 'MODEL_DERIVED_NOT_MEASURED_SOIL_MOISTURE',
        'rainfallSourceHashes': prior['sourceHashes'], 'evaporationSourceHashes': pet['sourceHashes'],
        'antecedentEvaporationMethod': pet['method'], 'rainfallQualityWarnings': prior.get('qualityWarnings', []),
        'zeroCounterDerivedMinutes': prior.get('reconstructedMinutes', 0),
        'aggregatedRainIntervals': prior.get('aggregatedRainIntervals', []),
        'aggregateDerivedMinutes': sum(v['minutes'] for v in prior.get('aggregatedRainIntervals', [])), 'seed': 'WILTING_POINT_AND_EMPTY_STORAGE',
        'limitations': []}
    if not legacy:
        value['initialization']['seedSaturationPercent'] = seed_percent
        value['initialization']['seed'] = ('WILTING_POINT_AND_EMPTY_STORAGE' if seed_percent == 0
                                          else 'SATURATED_SOIL_STORAGE_AND_DRAINMAT')
    value['initialization']['limitations'] = [
        f'선행 {warmup_minutes//1440}일 이전 수분 실측 미확보로 '+(
            '시들음점·빈 저류층에서 재생' if seed_percent == 0 else '토양·저류층·배수매트 포화 상태에서 재생'),
        '관측 기상 기반 모델 상태이며 현장 토양수분 측정값 아님',
        '시설이 선행 기간에 존재한 조건의 초기화이며 시공 직후 반입토 수분 복원 아님',
        f'{warmup_minutes//1440}일은 초기화 계산 기간이며 장기 건조기 초기조건의 완전 수렴을 보장하지 않음']
    if prior.get('qualityWarnings'):
        value['initialization']['limitations'].append('선행 강우 일누적 차분과 이동합 불일치 경고 보존; 원문 일누적을 우선한 초기화')
    if prior.get('aggregatedRainIntervals'):
        value['initialization']['limitations'].append('선행 통신 결측은 누적 관측 또는 동일 지점 시간 강우의 총량을 평균 강도로 적용; 분별 관측 복원 아님')
    if supplement := prior.get('supplement'):
        binding = supplement['binding']
        value['initialization']['rainfallSupplement'] = {
            'provider': 'SEOUL_OPEN_DATA', 'stationId': binding['secondary']['stationId'],
            'stationName': binding['secondary']['name'], 'distanceM': binding['distanceM'],
            'minutes': supplement['minutes'], 'fraction': supplement['fraction'],
            'sourceSha256': supplement['sourceSha256'], 'registrySha256': supplement['registrySha256']}
        value['initialization']['limitations'].append(
            f"선행 결측 {supplement['minutes']}분은 AWS에서 {binding['distanceM']/1000:.3f}km 떨어진 "
            f"서울시 {binding['secondary']['name']}의 10분 관측을 평균 강도로 적용; 현장·분별 실측값 아님")
    value['hydrology']['initialSaturationPercent'] = seed_percent
    value['assumptions'] = [s for s in value['assumptions'] if '초기 포화' not in s and '초기 수분' not in s]
    value['assumptions'] += value['initialization']['limitations']
    combined_pet = evaporation | {'ratesMmDay': pet['ratesMmDay']+evaporation['ratesMmDay'],
        'sourceHashes': sorted(set(pet['sourceHashes']+evaporation['sourceHashes'])),
        'antecedentMethod': pet['method'], 'antecedentMinutes': warmup_minutes}
    return value, combined_pet


def rebase(run, minutes):
    origin = run['samples'][minutes-1]
    def relative(state):
        current = dict(state)
        for key in CUMULATIVE:
            current[key] = None if state[key] is None else state[key]-origin[key]
        current['elapsedSeconds'] -= minutes*60
        current['initialStorageM3'] = origin['storageM3']
        current['lidInitialStorageM3'] = origin['lidStorageM3']
        current['accountedDischargeM3'] = (current['surfaceRunoffM3']+current['lidDrainageM3']
                                          +current['storageM3']-current['initialStorageM3'])
        current['balanceResidualM3'] = (current['precipitationM3']-current['evaporationM3']
                                       -current['infiltrationM3']-current['accountedDischargeM3'])
        return current
    samples = [relative(state) for state in run['samples'][minutes:]]
    return run | {'initial': relative(origin), 'samples': samples, 'final': samples[-1],
        'continuityCheckScope': 'FULL_WARMUP_AND_EVALUATION',
        'warmup': {'initial': run['initial'], 'final': origin, 'minutes': minutes}}


def evaluation_window(model, baseline, strategy):
    spec = model['initialization']
    minutes = spec.get('warmupMinutes')
    start = datetime.fromisoformat(model['rainfall']['start'])
    policy_valid = ((spec.get('method') == METHOD and minutes == MINUTES)
                    or (spec.get('method') == SENSITIVITY_METHOD
                        and type(minutes) is int and minutes in SUPPORTED_MINUTES
                        and type(spec.get('seedSaturationPercent')) is int
                        and spec['seedSaturationPercent'] in (0, 100)
                        and model['hydrology']['initialSaturationPercent'] == spec['seedSaturationPercent']))
    if (not policy_valid
            or datetime.fromisoformat(spec['evaluationStart']) != start+timedelta(minutes=minutes)
            or len(baseline['samples']) <= minutes or len(strategy['samples']) != len(baseline['samples'])):
        raise SimulationQualityError('LIVE_INITIALIZATION_INVALID')
    base, design = rebase(baseline, minutes), rebase(strategy, minutes)
    return base, design, spec | {'initialSoilMoisture': design['initial']['soilMoisture'],
        'initialStorageM3': design['initial']['storageM3'],
        'initialSurfaceDepthMm': design['initial']['surfaceDepthMm'],
        'initialStorageDepthMm': design['initial']['storageDepthMm'],
        'warmupRainMm': sum(model['rainfall']['depthsMm'][:minutes]),
        'scoreExcludesWarmup': True}
