"""사전 고정 노출영역과 평가 기간의 원 지표. 물리 상태·총점 수정 없음."""
import hashlib
import json
import math
from pathlib import Path

from waterleague_sim.engine.flood_errors import require


def validate_metrics(spec, triangle_count, duration_seconds=None):
    require(isinstance(spec, dict) and spec.get('schemaVersion') == 1
            and isinstance(spec.get('policyVersion'), str) and spec['policyVersion']
            and spec.get('evidence'), 'FLOOD_METRICS_REFERENCE_REQUIRED')
    start, end = spec.get('startMilliseconds'), spec.get('endMilliseconds')
    require(type(start) is int and type(end) is int and 0 <= start < end
            and (duration_seconds is None or end <= duration_seconds * 1000),
            'FLOOD_METRICS_WINDOW_INVALID')
    outfalls, cells = spec.get('networkOutfalls'), spec.get('exposureTriangles')
    require(isinstance(outfalls, list) and outfalls and all(isinstance(n, str) and n for n in outfalls)
            and len(set(outfalls)) == len(outfalls), 'FLOOD_METRICS_OUTFALLS_REQUIRED')
    # 빈 노출영역도 명시적으로 허용하되 빠진 영역을 전체 격자로 대체하지 않는다.
    require(isinstance(cells, list) and all(type(i) is int and 0 <= i < triangle_count for i in cells)
            and len(set(cells)) == len(cells),
            'FLOOD_METRICS_EXPOSURE_REQUIRED')
    threshold = spec.get('wetDepthThresholdM')
    require(type(threshold) in (int, float) and math.isfinite(threshold) and threshold >= 0,
            'FLOOD_METRICS_THRESHOLD_REQUIRED')


def specification_hash(spec):
    return hashlib.sha256(json.dumps(spec, sort_keys=True, separators=(',', ':'),
                                    ensure_ascii=False, allow_nan=False).encode()).hexdigest()


class DepthMetrics:
    """인접 내부 상태의 선형 보간 적분. 관측 콜백은 중심 상태를 읽기만 한다."""

    def __init__(self, domain, spec):
        import numpy as np
        validate_metrics(spec, len(domain.areas))
        self.np, self.domain, self.spec = np, domain, spec
        self.indices = np.asarray(spec['exposureTriangles'], dtype=int)
        self.areas = domain.areas[self.indices].copy()
        self.start, self.end = spec['startMilliseconds'] / 1000, spec['endMilliseconds'] / 1000
        self.threshold = spec['wetDepthThresholdM']
        self.previous_time = float(domain.get_time())
        require(self.previous_time == 0, 'FLOOD_METRICS_INITIAL_STATE_REQUIRED')
        self.previous = self._depth()
        self.depth_seconds = np.zeros(len(self.indices))
        self.wet_seconds = np.zeros(len(self.indices))
        self.maximum_depth = np.zeros(len(self.indices))
        self.maximum_wet_area = 0.
        self.elapsed = 0.
        self.steps = 0
        if self.start == 0:
            self._maxima(self.previous)
        domain.set_fractional_step_operator(self)

    def _depth(self):
        d = self.domain
        depth = (d.quantities['stage'].centroid_values[self.indices]
                 - d.quantities['elevation'].centroid_values[self.indices])
        require(self.np.all(self.np.isfinite(depth)) and self.np.all(depth >= -1e-10),
                'FLOOD_METRICS_DEPTH_INVALID')
        # 엔진의 미소 음수 허용 범위만 집계에서 0으로 취급하며 원 상태는 보존한다.
        return self.np.maximum(depth, 0)

    def _maxima(self, depth):
        self.np.maximum(self.maximum_depth, depth, out=self.maximum_depth)
        self.maximum_wet_area = max(self.maximum_wet_area,
            float(self.np.sum(self.areas[depth > self.threshold])))

    def reset_at_instant(self):
        now = float(self.domain.get_time())
        require(math.isclose(now, self.previous_time, rel_tol=0, abs_tol=1e-8),
                'FLOOD_METRICS_CLOCK_MISMATCH')
        self.previous = self._depth()
        if self.start <= now < self.end:
            self._maxima(self.previous)

    def __call__(self):
        before = float(self.domain.get_time())
        dt = float(self.domain.get_timestep())
        require(math.isclose(before, self.previous_time, rel_tol=0, abs_tol=1e-8)
                and math.isfinite(dt) and dt > 0, 'FLOOD_METRICS_CLOCK_MISMATCH')
        now = before + dt
        current = self._depth()
        left, right = max(before, self.start), min(now, self.end)
        if right > left:
            a = self.previous + (current - self.previous) * ((left - before) / dt)
            b = self.previous + (current - self.previous) * ((right - before) / dt)
            span = right - left
            self.depth_seconds += (a + b) * (.5 * span)
            wet_a, wet_b = a > self.threshold, b > self.threshold
            fraction = (wet_a & wet_b).astype(float)
            crossing = wet_a != wet_b
            crossing_time = self.np.divide(self.threshold - a, b - a,
                out=self.np.zeros_like(a), where=crossing)
            fraction[crossing] = self.np.where(wet_a[crossing],
                crossing_time[crossing], 1 - crossing_time[crossing])
            self.wet_seconds += fraction * span
            self._maxima(a)
            self._maxima(b)
            self.elapsed += span
            self.steps += 1
        self.previous_time, self.previous = now, current

    def snapshot(self):
        np = self.np
        return {'specificationSha256': specification_hash(self.spec),
            'adapterSha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'complete': math.isclose(self.elapsed, self.end - self.start, rel_tol=0, abs_tol=1e-7),
            'coveredSeconds': self.elapsed, 'nativeSteps': self.steps,
            'method': 'NATIVE_STEP_LINEAR_DEPTH_TRAPEZOIDAL_INTEGRAL',
            'maximumMethod': 'NATIVE_STEP_ENDPOINTS_AND_INSTANT_EXCHANGES',
            'exposureAreaM2': float(np.sum(self.areas)),
            'depthAreaTimeM3Hours': float(np.dot(self.depth_seconds, self.areas) / 3600),
            'maximumDepthM': float(np.max(self.maximum_depth, initial=0)),
            'maximumWetAreaM2': self.maximum_wet_area,
            'wetDepthThresholdM': self.threshold,
            'triangles': self.indices.tolist(), 'areasM2': self.areas.tolist(),
            'depthTimeMHours': (self.depth_seconds / 3600).tolist(),
            'wetDurationSeconds': self.wet_seconds.tolist(),
            'maximumDepthByTriangleM': self.maximum_depth.tolist()}

    def statistics(self):
        return '평가 노출영역 원 지표 관측'

    timestepping_statistics = statistics

    def log_timestepping_statistics(self):
        pass
