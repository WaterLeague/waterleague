"""ANUGA 내부 단계의 원 수지와 시간 간격 관측. 상태 변경 없음."""
import hashlib
import json
import math
from pathlib import Path

from waterleague_sim.engine.flood_errors import FloodModelError


class SurfaceQuality:
    def __init__(self, domain, initial_volume, directory):
        import numpy as np
        self.np, self.domain = np, domain
        self.initial_volume, self.directory = initial_volume, directory
        self.steps = 0
        self.last_time = float(domain.get_time())
        self.smallest = None
        self.largest = 0.
        self.maximum_absolute = 0.
        self.maximum_relative = 0.
        self.last = None
        self.failure_code = None
        self.source_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        domain.set_fractional_step_operator(self)

    def _fail(self, code):
        self.failure_code = code
        self.save()
        raise FloodModelError(code)

    def observe(self, time):
        np, d = self.np, self.domain
        depth = d.quantities['stage'].centroid_values - d.quantities['elevation'].centroid_values
        if not math.isfinite(time) or not all(np.all(np.isfinite(values)) for values in
                (depth, d.quantities['xmomentum'].centroid_values, d.quantities['ymomentum'].centroid_values)):
            self._fail('SURFACE_NATIVE_NONFINITE_STATE')
        storage = float(np.dot(depth, d.areas))
        boundary = float(d.get_boundary_flux_integral())
        forcing = float(d.get_fractional_step_volume_integral())
        if not all(math.isfinite(v) for v in (storage, boundary, forcing)):
            self._fail('SURFACE_NATIVE_NONFINITE_BALANCE')
        residual = self.initial_volume + boundary + forcing - storage
        scale = max(self.initial_volume + max(0., boundary) + max(0., forcing), storage)
        relative = 100 * abs(residual) / scale if scale > 0 else 0.
        self.maximum_absolute = max(self.maximum_absolute, abs(residual))
        self.maximum_relative = max(self.maximum_relative, relative)
        self.last = {'timeSeconds': time, 'storageM3': storage, 'boundaryNetInflowM3': boundary,
                     'sourceNetInflowM3': forcing, 'balanceResidualM3': residual,
                     'relativeResidualPercent': relative, 'minimumDepthM': float(np.min(depth))}
        if self.last['minimumDepthM'] < -1e-10:
            self._fail('SURFACE_NATIVE_NEGATIVE_DEPTH')
        if abs(residual) > max(1e-8, .01 * scale):
            self._fail('SURFACE_NATIVE_BALANCE_FAILED')

    def __call__(self):
        before, step = float(self.domain.get_time()), float(self.domain.get_timestep())
        if not math.isfinite(step) or step <= 0 or not math.isclose(before, self.last_time,
                                                                 abs_tol=1e-8, rel_tol=0):
            self._fail('SURFACE_NATIVE_CLOCK_MISMATCH')
        self.steps += 1
        self.smallest = step if self.smallest is None else min(self.smallest, step)
        self.largest = max(self.largest, step)
        self.last_time = before + step
        self.observe(self.last_time)

    def snapshot(self):
        return {'policyVersion': 'SURFACE_NATIVE_BALANCE_v1',
                'status': 'FAILED' if self.failure_code else 'PASSED', 'failureCode': self.failure_code,
                'nativeSteps': self.steps, 'lastInternalTimeSeconds': self.last_time,
                'minimumStepSeconds': self.smallest, 'maximumStepSeconds': self.largest,
                'maximumAbsoluteResidualM3': self.maximum_absolute,
                'maximumRelativeResidualPercent': self.maximum_relative, 'last': self.last,
                'relativeTolerancePercent': 1., 'absoluteToleranceM3': 1e-8,
                'sourceSha256': self.source_hash}

    def save(self):
        (self.directory / 'surface-quality.json').write_text(
            json.dumps(self.snapshot(), ensure_ascii=False, allow_nan=False, indent=2) + '\n')

    def statistics(self):
        return '지표 내부 단계 수지 관측'

    timestepping_statistics = statistics

    def log_timestepping_statistics(self):
        return None
