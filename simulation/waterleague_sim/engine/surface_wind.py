"""ANUGA 공식 풍응력 연산자의 SI 계수·젖은 격자·운동량 원장 연결."""
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from anuga.operators.wind_stress_operator import Wind_stress_operator
from waterleague_sim.engine.flood_errors import require


def grid_basis(domain, series, model):
    count = len(domain.areas)
    if series.basis == 'LOCAL_TRUE_EAST_NORTH_DIAGNOSTIC':
        return np.tile([1., 0.], (count, 1)), np.tile([0., 1.], (count, 1)), 0.
    from pyproj import Transformer, Geod
    inverse = Transformer.from_crs('EPSG:5186', 'EPSG:4326', always_xy=True)
    forward = Transformer.from_crs('EPSG:4326', 'EPSG:5186', always_xy=True)
    centers = domain.centroid_coordinates
    lon, lat = inverse.transform(centers[:, 0], centers[:, 1])
    require(np.all(np.isfinite(lon)) and np.all(np.isfinite(lat))
            and np.all((124 < lon) & (lon < 132) & (32 < lat) & (lat < 40)), 'WIND_PROJECTED_LOCATION_INVALID')
    geod = Geod(ellps='WGS84')
    bases = []
    for distance in (1., .5):
        vectors = []
        for azimuth in (90., 0.):
            lo, la, _ = geod.fwd(lon, lat, np.full(count, azimuth), np.full(count, distance))
            x, y = forward.transform(lo, la)
            vector = np.column_stack((x-centers[:, 0], y-centers[:, 1]))
            length = np.linalg.norm(vector, axis=1)
            require(np.all(np.isfinite(vector)) and np.all(length > 0), 'WIND_GRID_BASIS_INVALID')
            vectors.append(vector/length[:, None])
        bases.append(vectors)
    difference = max(float(np.max(np.abs(a-b))) for a, b in zip(*bases))
    east, north = bases[0]
    require(difference <= 1e-6 and np.max(np.abs(np.sum(east*north, axis=1))) <= 1e-6
            and np.all(east[:, 0]*north[:, 1]-east[:, 1]*north[:, 0] > 0), 'WIND_GRID_BASIS_UNSTABLE')
    return east, north, difference


class SurfaceWind(Wind_stress_operator):
    def __init__(self, domain, series, model, directory):
        super().__init__(domain, speed=0., phi=0.)
        from anuga.config import eta_w, rho_a, rho_w
        self.upstream_defaults = {'eta_w': eta_w, 'rho_a': rho_a, 'rho_w': rho_w}
        self.series = series
        self.directory = directory
        self.east, self.north, self.basis_error = grid_basis(domain, series, model)
        self.source_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        self.impulse = np.zeros(2)
        self.work = 0.
        self.steps, self.dry_skips = 0, 0
        self.maximum_relaxation = 0.
        self.wet_depth = float(domain.minimum_allowed_height)
        self.basis_hash = hashlib.sha256(np.column_stack((self.east, self.north)).tobytes()).hexdigest()
        self.const = series.air_density / series.water_density

    def __call__(self):
        d, s = self.domain, self.series
        dt = float(d.get_timestep())
        u, v = s.vector(float(d.get_time()), dt)
        depth = d.quantities['stage'].centroid_values - d.quantities['elevation'].centroid_values
        require(np.all(np.isfinite(depth)) and np.min(depth) >= -1e-10, 'WIND_NONPHYSICAL_DEPTH')
        wet = depth > self.wet_depth
        before = np.column_stack((self.xmom_c.copy(), self.ymom_c.copy()))
        water = np.divide(before, depth[:, None], out=np.zeros_like(before), where=wet[:, None])
        relative = u*self.east + v*self.north - water
        relative[~wet] = 0.
        speed = np.linalg.norm(relative, axis=1)
        if s.drag_law == 'GARRATT_HEC_6_6':
            require(np.max(speed) <= 30, 'WIND_DRAG_VALIDITY_RANGE_EXCEEDED')
            drag = np.clip(.001*(.75+.067*speed), .00075, .00264)
        else:
            drag = np.full(len(depth), s.constant_drag)
        # SI 밀도를 명시하고 해수/혼합 단위 기본값이 계산에 스며들지 않게 한다.
        self.const = drag*s.air_density/s.water_density
        relaxation = np.divide(dt*self.const*speed, depth, out=np.zeros_like(depth), where=wet)
        if s.integration == 'ANUGA_EXPLICIT_DIAGNOSTIC_V1':
            if np.max(relaxation) > .25:
                self.save(self.directory)
                (self.directory/'surface-wind-failure.json').write_text(json.dumps({
                    'code': 'WIND_TIMESTEP_UNSTABLE', 'timeSeconds': float(d.get_time()),
                    'stepSeconds': dt, 'maximumExplicitRelaxation': float(np.max(relaxation)),
                    'minimumWetDepthM': float(np.min(depth[wet]))}, allow_nan=False)+'\n')
                require(False, 'WIND_TIMESTEP_UNSTABLE')
        else:
            # 단계 내 항력을 고정한 상대속도 이차 ODE의 해로 얕은 물의 과도 가속을 방지한다.
            self.const = self.const/(1+relaxation)
        self.maximum_relaxation = max(self.maximum_relaxation, float(np.max(relaxation)))
        self.speed = lambda t, x, y: speed
        self.phi = lambda t, x, y: np.degrees(np.arctan2(relative[:, 1], relative[:, 0]))
        volume_before = float(d.get_fractional_step_volume_integral())
        super().__call__()
        after = np.column_stack((self.xmom_c, self.ymom_c))
        require(np.all(np.isfinite(after)) and np.array_equal(before[~wet], after[~wet])
                and volume_before == float(d.get_fractional_step_volume_integral())
                and np.array_equal(depth, d.quantities['stage'].centroid_values-d.quantities['elevation'].centroid_values),
                'WIND_NON_MOMENTUM_CHANGE')
        self.impulse += s.water_density*np.sum((after-before)*d.areas[:, None], axis=0)
        energy = np.divide(np.sum(after**2-before**2, axis=1), 2*depth,
                           out=np.zeros_like(depth), where=wet)
        self.work += s.water_density*float(np.dot(energy, d.areas))
        self.steps += 1
        self.dry_skips += int(np.count_nonzero(~wet))

    def summary(self):
        return self.series.summary | {'adapterSha256': self.source_hash,
            'upstreamOperator': 'anuga.operators.wind_stress_operator.Wind_stress_operator',
            'upstreamDefaultsNotApplied': self.upstream_defaults,
            'nativeSteps': self.steps, 'dryTriangleStepsSkipped': self.dry_skips,
            'dryThresholdM': self.wet_depth, 'waterVolumeAddedM3': 0.,
            'impulseXKgMps': float(self.impulse[0]), 'impulseYKgMps': float(self.impulse[1]),
            'workOnWaterJ': self.work, 'maximumExplicitRelaxation': self.maximum_relaxation,
            'maximumAllowedExplicitRelaxation': .25 if self.series.integration == 'ANUGA_EXPLICIT_DIAGNOSTIC_V1' else None,
            'basisSha256': self.basis_hash, 'basisDistanceConvergenceError': self.basis_error,
            'splittingPolicy': 'FLOW_RAIN_INFILTRATION_EVAPORATION_THEN_RELATIVE_WIND',
            'complete': math.isclose(float(self.domain.get_time()), self.series.duration, rel_tol=0, abs_tol=1e-8)}

    def save(self, directory):
        (directory / 'surface-wind.json').write_text(json.dumps(
            self.summary(), ensure_ascii=False, allow_nan=False, indent=2)+'\n')
