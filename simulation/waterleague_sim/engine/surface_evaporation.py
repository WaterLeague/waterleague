"""시간별 잠재 증발 입력을 가용 지표수로 제한하는 체적 연산."""
import hashlib
import math
from pathlib import Path

from waterleague_sim.engine.flood_errors import require


class SurfaceEvaporation:
    def __init__(self, domain, series, owners, surface_fractions=None):
        import numpy as np
        self.np, self.domain, self.series = np, domain, series
        self.indices = np.flatnonzero(np.asarray(owners) == 'SURFACE')
        self.fractions = (np.ones(len(self.indices)) if surface_fractions is None
                          else np.asarray(surface_fractions)[self.indices])
        require(len(self.indices) > 0, 'EVAPORATION_SURFACE_AREA_REQUIRED')
        self.cumulative = np.zeros(len(self.indices))
        self.potential_volume = 0.
        self.unmet_volume = 0.
        self.steps = 0
        self.source_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        domain.set_fractional_step_operator(self)

    def __call__(self):
        np, domain, cells = self.np, self.domain, self.indices
        potential_depth = self.series.step_depth_m(float(domain.get_time()), float(domain.get_timestep()))
        stage = domain.quantities['stage'].centroid_values
        z = domain.quantities['elevation'].centroid_values
        depth = stage[cells] - z[cells]
        require(np.all(np.isfinite(depth)) and np.all(depth >= -1e-10), 'EVAPORATION_NONPHYSICAL_DEPTH')
        removal = np.minimum(potential_depth, np.maximum(0., depth)) * self.fractions
        before = stage[cells].copy()
        stage[cells] = before - removal
        actual = before - stage[cells]
        require(np.all(np.abs(actual - removal) <= 1e-10), 'EVAPORATION_ROUNDOFF_EXCEEDED')
        ratio = np.divide(stage[cells] - z[cells], depth, out=np.ones_like(depth), where=depth > 0)
        for name in ('xmomentum', 'ymomentum'):
            domain.quantities[name].centroid_values[cells] *= ratio
        volumes = actual * domain.areas[cells]
        self.cumulative += volumes
        self.potential_volume += potential_depth * float(np.dot(domain.areas[cells], self.fractions))
        self.unmet_volume += float(np.dot(potential_depth*self.fractions - removal, domain.areas[cells]))
        domain.fractional_step_volume_integral -= float(np.sum(volumes))
        self.steps += 1

    def ledger(self):
        actual = float(self.np.sum(self.cumulative))
        return {'potentialSurfaceEvaporationM3': self.potential_volume, 'surfaceEvaporationM3': actual,
                'unmetSurfaceEvaporationM3': self.unmet_volume,
                'surfaceEvaporationRoundoffM3': actual - (self.potential_volume - self.unmet_volume)}

    def summary(self, *, include_state=False):
        area = float(self.np.dot(self.domain.areas[self.indices], self.fractions))
        expected = self.series.summary['potentialDepthMm'] * area / 1000
        complete = math.isclose(float(self.domain.get_time()), self.series.duration, abs_tol=1e-8, rel_tol=0)
        if complete:
            require(math.isclose(expected, self.potential_volume, abs_tol=1e-8, rel_tol=1e-8),
                    'EVAPORATION_POTENTIAL_VOLUME_MISMATCH')
        result = self.series.summary | self.ledger() | {
            'sourceSha256': self.source_hash, 'nativeSteps': self.steps,
            'surfaceAreaM2': area, 'complete': complete,
            'expectedFullWindowPotentialM3': expected,
            'splittingPolicy': 'FLOW_RAIN_INFILTRATION_THEN_WATER_LIMITED_EVAPORATION',
            'momentumPolicy': 'PROPORTIONAL_WATER_WITHDRAWAL',
            'limitations': ['기준 잔디 증발산의 지표수 전용은 미보정 가정; 현장 수면 증발 관측 아님',
                '지표의 고인 물만 제거; 토양·식물·지하수 수분 인출 미포함',
                '명시적 분할 오차의 시간 세분 비교 필요']}
        if include_state:
            result.update(triangles=self.indices.tolist(), evaporationByTriangleM3=self.cumulative.tolist())
        return result

    def statistics(self):
        return '가용 지표수 제한 증발'

    timestepping_statistics = statistics

    def log_timestepping_statistics(self):
        return None
