"""설치 경계의 실제 엔진 상태를 빼서 선행 기간과 실험 점수를 분리."""
from datetime import datetime, timedelta

from .initialization import CUMULATIVE
from .swmm import SimulationQualityError

POLICY = 'INSTALLATION_TIME_EXPERIMENT_V1'


def installation_offset(model, installed_at):
    try:
        start, end = (datetime.fromisoformat(model['rainfall'][key]) for key in ('start', 'end'))
        at = datetime.fromisoformat(installed_at)
        evaluation = datetime.fromisoformat(model.get('initialization', {}).get('evaluationStart', start.isoformat()))
        seconds = (at-start).total_seconds()
        if at.utcoffset() is None or at.microsecond or not evaluation <= at < end or not seconds.is_integer():
            raise ValueError()
        return int(seconds)
    except (ValueError, TypeError, KeyError):
        raise SimulationQualityError('HISTORICAL_INSTALLATION_TIME_INVALID') from None


def rebase_activation(run, offset):
    origin = run['evaluationOrigin']
    if abs(origin['elapsedSeconds']-offset) > 1e-7:
        raise SimulationQualityError('HISTORICAL_INSTALLATION_STATE_MISSING')

    def relative(state):
        value = dict(state)
        for key in CUMULATIVE:
            value[key] = None if state[key] is None else state[key]-origin[key]
        value['elapsedSeconds'] -= offset
        value['initialStorageM3'] = origin['storageM3']
        value['lidInitialStorageM3'] = origin['lidStorageM3']
        value['accountedDischargeM3'] = (value['surfaceRunoffM3']+value['lidDrainageM3']
                                        +value['storageM3']-value['initialStorageM3'])
        value['balanceResidualM3'] = (value['precipitationM3']-value['evaporationM3']
                                    -value['infiltrationM3']-value['accountedDischargeM3'])
        return value

    samples = [relative(s) for s in run['samples'] if s['elapsedSeconds'] > offset]
    final = samples[-1]
    if abs(final['balanceResidualM3']) > max(1e-8, .01*(final['precipitationM3']+final['initialStorageM3'])):
        raise SimulationQualityError('HISTORICAL_EVALUATION_BALANCE_FAILED')
    return run | {'initial': relative(origin), 'samples': samples, 'final': samples[-1],
        'continuityCheckScope': 'FULL_WARMUP_AND_EVALUATION',
        'preActivation': {'initial': run['initial'], 'final': origin, 'seconds': offset}}


def activation_window(model, baseline, strategy, offset):
    base, design = rebase_activation(baseline, offset), rebase_activation(strategy, offset)
    start = datetime.fromisoformat(model['rainfall']['start'])
    whole, remainder = divmod(offset, 60)
    rain = model['rainfall']['depthsMm']
    initialization = model.get('initialization', {}) | {
        'method': POLICY, 'evaluationStart': (start+timedelta(seconds=offset)).isoformat(),
        'preActivationSeconds': offset, 'scoreExcludesWarmup': True,
        'initialSoilMoisture': design['initial']['soilMoisture'],
        'initialStorageM3': design['initial']['storageM3'],
        'initialSurfaceDepthMm': design['initial']['surfaceDepthMm'],
        'initialStorageDepthMm': design['initial']['storageDepthMm'],
        'warmupRainMm': sum(rain[:whole]) + (rain[whole]*remainder/60 if remainder else 0),
        'limitations': list(model.get('initialization', {}).get('limitations', [])) + [
            '설치 시각 이전은 시설 상태 준비 계산으로만 사용하며 표시·점수에서 제외',
            '시설이 선행 기간에 존재한 조건의 수분·저류 상태이며 시공 직후 상태 측정값 아님',
            '분 강우는 해당 분 내 균일 강도 가정; 설치 경계는 원 1초 적분 상태로 분리',
            '결과 표시는 분 종료 시각이며 아직 도달하지 않은 미래 기록은 누적 점수에 미포함']}
    return base, design, initialization
