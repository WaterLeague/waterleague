"""선택 표면의 원 계산 단계별 유출·배수 첨두와 평가 물수지 비교."""
from datetime import timedelta
import hashlib
import math
from pathlib import Path

from .swmm import SimulationQualityError

METHOD = 'NATIVE_RUNOFF_STEP_SURFACE_PLUS_DRAIN_V1'
TIMING_METHOD = 'NATIVE_RUNOFF_VOLUME_CENTROID_V1'


def require(condition):
    if not condition:
        raise SimulationQualityError('LIVE_RUNOFF_METRICS_INVALID')


class RunoffMetrics:
    def __init__(self, start, end, clock, expected_step):
        require(0 <= start < end and expected_step > 0)
        self.start, self.end, self.clock = start, end, clock
        self.expected_step = expected_step
        self.previous = 0.
        self.seconds = self.volume = self.compensation = 0.
        self.moment = self.moment_compensation = 0.
        self.peak = self.max_step = 0.
        self.peak_at = None
        self.steps = 0
        self.minimum_flow = 0.

    def observe(self, seconds, surface, drain):
        require(math.isfinite(seconds) and seconds >= 0
                and all(math.isfinite(v) and v >= -1e-9 for v in (surface, drain)))
        step = seconds - self.previous
        # 표면·배수 유량을 같은 내부 단계에서 더하고 기록 주기와 독립적으로 관측한다.
        require(abs(step - self.expected_step) <= 1e-7 and seconds <= self.end + 1e-7)
        if seconds > self.start:
            require(self.previous >= self.start - 1e-7)
            flow = surface + drain
            require(math.isfinite(flow))
            self.minimum_flow = min(self.minimum_flow, surface, drain)
            volume = flow * step
            corrected = volume - self.compensation
            summed = self.volume + corrected
            self.compensation = (summed - self.volume) - corrected
            self.volume = summed
            # 내부 구간 평균 유량의 1차 모멘트는 구간 중점을 사용하고 선행 시간을 뺀다.
            moment = volume * (self.previous + step / 2 - self.start)
            corrected_moment = moment - self.moment_compensation
            summed_moment = self.moment + corrected_moment
            self.moment_compensation = (summed_moment - self.moment) - corrected_moment
            self.moment = summed_moment
            require(math.isfinite(self.volume) and math.isfinite(self.moment))
            self.seconds += step
            self.steps += 1
            self.max_step = max(self.max_step, step)
            if flow > self.peak:
                self.peak, self.peak_at = flow, seconds
        self.previous = seconds

    def finish(self):
        require(abs(self.previous - self.end) <= 1e-7
                and abs(self.seconds - (self.end - self.start)) <= 1e-7 and self.steps > 0)
        at = lambda t: (self.clock + timedelta(seconds=t)).isoformat()
        reason = ('NEGATIVE_COMPONENT_RATE' if self.minimum_flow < 0
                  else 'NO_DISCHARGE' if self.volume == 0 else None)
        centroid = None if reason else self.moment / self.volume
        require(centroid is None or math.isfinite(centroid) and 0 <= centroid <= self.seconds)
        return {'method': METHOD, 'scope': 'SELECTED_SURFACE_OUTLET_NOT_SEWER_OR_RIVER',
            'start': at(self.start), 'end': at(self.end), 'stepCount': self.steps,
            'maximumStepSeconds': self.max_step, 'observedSeconds': self.seconds,
            'dischargeIntegralM3': self.volume, 'peakM3s': self.peak,
            'peakAt': None if self.peak_at is None else at(self.peak_at),
            'peakTimeConvention': 'END_OF_NATIVE_RUNOFF_INTERVAL',
            'minimumComponentRateM3s': self.minimum_flow,
            'timing': {'method': TIMING_METHOD, 'firstMomentM3Seconds': self.moment,
                'centroidSeconds': centroid,
                'status': 'WITHHELD' if reason == 'NEGATIVE_COMPONENT_RATE' else 'UNAVAILABLE' if reason else 'COMPUTED',
                'reason': reason},
            'implementationSha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}


def comparison(baseline, strategy):
    cases = []
    for name, run in (('baseline', baseline), ('strategy', strategy)):
        final, initial, metrics = run['final'], run['initial'], run['runoffMetrics']
        discharge = final['surfaceRunoffM3'] + final['lidDrainageM3']
        require(metrics['start'] == initial['at'] and metrics['end'] == final['at'])
        difference = metrics['dischargeIntegralM3'] - discharge
        require(abs(difference) <= max(1e-8, abs(discharge) * 1e-7))
        cases.append({'id': name, 'dischargeM3': discharge,
            'initialStorageM3': final['initialStorageM3'], 'finalStorageM3': final['storageM3'],
            'netStorageM3': final['storageM3'] - final['initialStorageM3'],
            'accountedDischargeM3': final['accountedDischargeM3'],
            'precipitationM3': final['precipitationM3'], 'infiltrationM3': final['infiltrationM3'],
            'evaporationM3': final['evaporationM3'], 'balanceResidualM3': final['balanceResidualM3'],
            'nativeIntegralDifferenceM3': difference, 'metrics': metrics})
    a, b = cases
    require(a['metrics']['start'] == b['metrics']['start'] and a['metrics']['end'] == b['metrics']['end'])
    timings = [c['metrics']['timing'] for c in cases]
    invalid = next(((label, t) for label, t in zip(('BASELINE', 'STRATEGY'), timings)
                    if t['status'] == 'WITHHELD'), None)
    missing = next(((label, t) for label, t in zip(('BASELINE', 'STRATEGY'), timings)
                    if t['status'] == 'UNAVAILABLE'), None)
    blocker = invalid or missing
    detention = {'schemaVersion': 1, 'method': TIMING_METHOD,
        'status': 'WITHHELD' if invalid else 'UNAVAILABLE' if missing else 'COMPARABLE',
        'reason': blocker[0] + '_' + blocker[1]['reason'] if blocker else None,
        'centroidDelaySeconds': None if blocker else timings[1]['centroidSeconds'] - timings[0]['centroidSeconds'],
        'evaluationWindowOnly': True, 'rankingEligible': False}
    value = {'schemaVersion': 3, 'method': METHOD, 'cases': cases,
        'dischargeReductionM3': a['dischargeM3'] - b['dischargeM3'],
        'netStorageIncreaseM3': b['netStorageM3'] - a['netStorageM3'],
        'accountedReductionM3': a['accountedDischargeM3'] - b['accountedDischargeM3'],
        'peakReductionM3s': a['metrics']['peakM3s'] - b['metrics']['peakM3s'],
        'detention': detention,
        'limitations': ['선택 표면 출구의 유출·하부배수 합이며 하수관·하천·구 전체 첨두 아님',
            '첨두는 내부 유출 계산 구간의 평균률 최대값과 그 구간 종료 시각',
            '선행 초기화 제외·평가 종료 후 방류 미포함; 잔여 저류를 영구 저감으로 취급하지 않음',
            '개별 표면 첨두 합산으로 연결 유역 첨두를 만들지 않음',
            '중심시각 지연은 평가 창 내 배출 시간 분포 차이; 종료 이후 배출·입자 체류시간·하류 침수 개선 아님']}
    from ..evaluation.raw_metrics import surface
    value['metricComparison'] = surface(value)
    return value
