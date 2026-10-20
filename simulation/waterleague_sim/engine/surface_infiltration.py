"""원본 EPA Green–Ampt의 영역별 상태와 ANUGA 침투 체적 연결."""
from copy import deepcopy
import ctypes as C
import hashlib
import json
import math
from pathlib import Path
import platform
import threading
import weakref

from waterleague_sim.engine.flood_errors import require
from waterleague_sim.engine.swmm import ROOT, REVISION

_LOCK = threading.Lock()


def library_path():
    return ROOT / 'tmp/surface-infiltration-build/src/solver' / (
        'libswmm5.dylib' if platform.system() == 'Darwin' else 'libswmm5.so')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def identity():
    library = library_path()
    require(library.is_file(), 'SURFACE_INFILTRATION_ENGINE_REQUIRED')
    try:
        build = json.loads((library.parent / 'soil-build.json').read_text())
    except (OSError, ValueError):
        require(False, 'SURFACE_INFILTRATION_IDENTITY_INVALID')
    require(build.get('engineVersion') == '5.2.4' and build.get('revision') == REVISION
            and build.get('openMP') is False and build.get('binarySha256') == sha(library)
            and build.get('extensionSha256') == sha(ROOT / 'simulation/native/surface_infiltration.inc')
            and build.get('builderSha256') == sha(ROOT / 'scripts/build_surface_infiltration.py'),
            'SURFACE_INFILTRATION_IDENTITY_MISMATCH')
    return build | {'adapterSha256': sha(__file__)}


def _number(value, low, high, *, inclusive=True):
    return (type(value) in (int, float) and math.isfinite(value)
            and (low <= value if inclusive else low < value) and value <= high)


def validate(specification, owners):
    require(isinstance(specification, dict) and type(specification.get('schemaVersion')) is int
            and specification['schemaVersion'] in (1, 2)
            and specification.get('method') in ('GREEN_AMPT', 'MODIFIED_GREEN_AMPT')
            and specification.get('ownershipPolicy') == 'SURFACE_ONLY'
            and specification.get('initialization') == 'EPA_INITIAL_DEFICIT_SEED'
            and specification.get('evidence')
            and _number(specification.get('recoveryFactor'), 0, 100, inclusive=False),
            'SURFACE_INFILTRATION_SPECIFICATION_INVALID')
    if specification['schemaVersion'] == 2:
        return validate_partition(specification, owners)
    sealed, regions = specification.get('imperviousTriangles'), specification.get('regions')
    require(isinstance(sealed, list) and isinstance(regions, list)
            and 0 < len(regions) <= len(owners), 'SURFACE_INFILTRATION_REGIONS_REQUIRED')
    seen = set()
    for row in [{'triangles': sealed}] + regions:
        require(isinstance(row, dict), 'SURFACE_INFILTRATION_REGION_INVALID')
        cells = row.get('triangles')
        require(isinstance(cells, list) and all(type(i) is int and 0 <= i < len(owners)
                for i in cells) and len(set(cells)) == len(cells) and not seen.intersection(cells),
                'SURFACE_INFILTRATION_REGION_INVALID')
        require(all(owners[i] == 'SURFACE' for i in cells), 'SURFACE_INFILTRATION_DOUBLE_COUNT')
        seen.update(cells)
    require(seen == {i for i, owner in enumerate(owners) if owner == 'SURFACE'},
            'SURFACE_INFILTRATION_COVERAGE_INCOMPLETE')
    for row in regions:
        require(row['triangles'] and row.get('evidence')
                and _number(row.get('perviousFraction'), 0, 1, inclusive=False)
                and _number(row.get('suctionMm'), 0, 100_000)
                and _number(row.get('conductivityMmH'), 0, 100_000, inclusive=False)
                and _number(row.get('initialMoistureDeficit'), 0, 1),
                'SURFACE_INFILTRATION_PARAMETERS_INVALID')
    return deepcopy(specification)


def validate_partition(specification, owners):
    regions, sealed = specification.get('regions'), specification.get('imperviousRegions')
    require(specification.get('partitionPolicy') == 'EXPLICIT_AREA_FRACTIONS'
            and 'imperviousTriangles' not in specification
            and isinstance(regions, list) and len(regions) <= 200_000
            and isinstance(sealed, list) and len(sealed) <= 200_000,
            'SURFACE_INFILTRATION_PARTITION_INVALID')
    fractions = [[] for _ in owners]
    entries = 0
    for pervious, rows in ((True, regions), (False, sealed)):
        for row in rows:
            require(isinstance(row, dict), 'SURFACE_INFILTRATION_REGION_INVALID')
            cells = row.get('triangles')
            require(isinstance(cells, list) and cells and all(type(i) is int and 0 <= i < len(owners)
                    for i in cells) and len(set(cells)) == len(cells),
                    'SURFACE_INFILTRATION_REGION_INVALID')
            require(all(owners[i] == 'SURFACE' for i in cells), 'SURFACE_INFILTRATION_DOUBLE_COUNT')
            entries += len(cells)
            require(entries <= 200_000, 'SURFACE_INFILTRATION_STATE_LIMIT')
            fraction = row.get('perviousFraction' if pervious else 'areaFraction')
            require(row.get('evidence') and _number(fraction, 0, 1, inclusive=False),
                    'SURFACE_INFILTRATION_PARAMETERS_INVALID')
            if pervious:
                require(_number(row.get('suctionMm'), 0, 100_000)
                        and _number(row.get('conductivityMmH'), 0, 100_000, inclusive=False)
                        and _number(row.get('initialMoistureDeficit'), 0, 1),
                        'SURFACE_INFILTRATION_PARAMETERS_INVALID')
            for cell in cells:
                fractions[cell].append(fraction)
    for owner, parts in zip(owners, fractions):
        total = math.fsum(parts)
        require(total <= 1 + 1e-12, 'SURFACE_INFILTRATION_AREA_OVERLAP')
        require(owner != 'SURFACE' or abs(total - 1) <= 1e-12,
                'SURFACE_INFILTRATION_COVERAGE_INCOMPLETE')
    return deepcopy(specification)


class SoilBank:
    """침투 상태를 연속 유지하는 배치. 다른 EPA 라이브러리의 전역 상태와 격리."""

    def __init__(self, parameters):
        import numpy as np
        self.np, self.engine = np, identity()
        self.lib = C.CDLL(str(library_path()))
        vector = np.ctypeslib.ndpointer(dtype=np.float64, flags='C_CONTIGUOUS')
        self.lib.wl_soilCreate.argtypes = [C.c_int, vector]
        self.lib.wl_soilCreate.restype = C.c_void_p
        self.lib.wl_soilAdvance.argtypes = [C.c_void_p, C.c_int, C.c_double, C.c_int,
                                           C.c_double, vector, vector, vector]
        self.lib.wl_soilState.argtypes = [C.c_void_p, C.c_int, vector]
        self.lib.wl_soilRelease.argtypes = [C.c_void_p]
        self.lib.wl_soilRelease.restype = None
        require(self.lib.wl_soilVersion() == 1, 'SURFACE_INFILTRATION_VERSION_MISMATCH')
        parameters = np.ascontiguousarray(parameters, dtype=float)
        require(parameters.ndim == 2 and parameters.shape[1] == 3
                and 1 <= len(parameters) <= 200_000, 'SURFACE_INFILTRATION_PARAMETERS_INVALID')
        self.count = len(parameters)
        with _LOCK:
            self.pointer = self.lib.wl_soilCreate(self.count, parameters)
        require(self.pointer, 'SURFACE_INFILTRATION_INITIALIZATION_FAILED')
        self._release = weakref.finalize(self, self.lib.wl_soilRelease, self.pointer)

    def advance(self, seconds, rates_mps, ponded_m, *, modified, recovery):
        np = self.np
        rain, ponded = [np.ascontiguousarray(v, dtype=float) for v in (rates_mps, ponded_m)]
        require(rain.shape == ponded.shape == (self.count,), 'SURFACE_INFILTRATION_FORCING_INVALID')
        result = np.empty(self.count)
        with _LOCK:
            error = self.lib.wl_soilAdvance(self.pointer, self.count, seconds, int(modified),
                                             recovery, rain, ponded, result)
        require(error == 0, 'SURFACE_INFILTRATION_NATIVE_FAILED')
        return result

    def state(self):
        values = self.np.empty((self.count, 5))
        with _LOCK:
            error = self.lib.wl_soilState(self.pointer, self.count, values)
        require(error == 0 and self.np.all(self.np.isfinite(values)),
                'SURFACE_INFILTRATION_STATE_INVALID')
        return values


class SurfaceInfiltration:
    def __init__(self, domain, rain, specification, owners, surface_fractions=None):
        import numpy as np
        self.np, self.domain, self.rain = np, domain, rain
        self.specification = validate(specification, owners)
        indices, fractions, parameters = [], [], []
        for row in self.specification['regions']:
            indices.extend(row['triangles'])
            fractions.extend([row['perviousFraction']] * len(row['triangles']))
            parameters.extend([[row['suctionMm'], row['conductivityMmH'], row['initialMoistureDeficit']]]
                               * len(row['triangles']))
        self.indices, self.fractions = np.asarray(indices, dtype=int), np.asarray(fractions, dtype=float)
        self.rainfall_fractions = (np.ones(len(owners)) if surface_fractions is None
                                  else np.asarray(surface_fractions))
        self.fractions *= self.rainfall_fractions[self.indices]
        self.cells, self.cell_inverse = np.unique(self.indices, return_inverse=True)
        self.bank = SoilBank(parameters) if parameters else None
        self.engine = self.bank.engine if self.bank else identity()
        self.cumulative = np.zeros(len(indices))
        self.roundoff_m3 = 0.
        self.steps = 0
        domain.set_fractional_step_operator(self)

    def __call__(self):
        np, domain, cells = self.np, self.domain, self.indices
        if not len(cells):
            self.steps += 1
            return
        dt = float(domain.get_timestep())
        stage = domain.quantities['stage'].centroid_values
        z = domain.quantities['elevation'].centroid_values
        depth = stage[cells] - z[cells]
        rates = self.rain.rate[cells] / 3_600_000
        rain_depth = rates * dt
        require(np.all(depth >= rain_depth - 1e-10), 'SURFACE_INFILTRATION_RAIN_ORDER_INVALID')
        # 방금 더한 강우는 유입률로, 흐름 계산 후 남은 물은 고인 수심으로 전달한다.
        local_rates = rates / self.rainfall_fractions[cells]
        infiltration = self.bank.advance(dt, local_rates, np.maximum(0., depth - rain_depth),
            modified=self.specification['method'] == 'MODIFIED_GREEN_AMPT',
            recovery=self.specification['recoveryFactor'])
        if self.specification['schemaVersion'] == 2:
            self._remove_partitioned(infiltration)
            self.steps += 1
            return
        removal = infiltration * self.fractions
        require(np.all(removal <= depth + 1e-12), 'SURFACE_INFILTRATION_OVERDRAW')
        removal = np.minimum(removal, np.maximum(0., depth))
        before = stage[cells].copy()
        stage[cells] = z[cells] + np.maximum(0., depth - removal)
        actual = before - stage[cells]
        require(np.all(np.abs(actual - removal) <= 1e-10), 'SURFACE_INFILTRATION_ROUNDOFF_EXCEEDED')
        ratio = np.divide(stage[cells] - z[cells], depth, out=np.ones_like(depth), where=depth > 0)
        for name in ('xmomentum', 'ymomentum'):
            domain.quantities[name].centroid_values[cells] *= ratio
        volumes = actual * domain.areas[cells]
        self.cumulative += volumes
        domain.fractional_step_volume_integral -= float(np.sum(volumes))
        self.steps += 1

    def _remove_partitioned(self, infiltration):
        np, domain, cells = self.np, self.domain, self.cells
        stage = domain.quantities['stage'].centroid_values
        z = domain.quantities['elevation'].centroid_values
        depth = stage[cells] - z[cells]
        requested = infiltration * self.fractions
        # 독립 토양 상태의 손실을 합산한 뒤 같은 삼각형에서 한 번만 인출한다.
        removal = np.bincount(self.cell_inverse, weights=requested, minlength=len(cells))
        require(np.all(removal <= depth + 1e-12), 'SURFACE_INFILTRATION_OVERDRAW')
        before = stage[cells].copy()
        stage[cells] = z[cells] + np.maximum(0., depth - np.minimum(removal, np.maximum(0., depth)))
        actual = before - stage[cells]
        require(np.all(np.abs(actual - removal) <= 1e-10), 'SURFACE_INFILTRATION_ROUNDOFF_EXCEEDED')
        ratio = np.divide(stage[cells] - z[cells], depth, out=np.ones_like(depth), where=depth > 0)
        for name in ('xmomentum', 'ymomentum'):
            domain.quantities[name].centroid_values[cells] *= ratio
        allocation = np.divide(actual, removal, out=np.zeros_like(actual), where=removal > 0)
        self.cumulative += requested * allocation[self.cell_inverse] * domain.areas[self.indices]
        volumes = actual * domain.areas[cells]
        self.roundoff_m3 += float(np.dot(actual - removal, domain.areas[cells]))
        domain.fractional_step_volume_integral -= float(np.sum(volumes))

    def summary(self, *, include_state=False):
        result = {'method': self.specification['method'], 'engine': self.engine,
            'infiltrationM3': float(self.np.sum(self.cumulative)), 'nativeSteps': self.steps,
            'effectivePerviousAreaM2': float(self.np.dot(self.domain.areas[self.indices], self.fractions)),
            'ownershipPolicy': 'SURFACE_ONLY', 'rankingEligible': False,
            'initialization': self.specification['initialization'],
            'momentumPolicy': 'PROPORTIONAL_WATER_WITHDRAWAL',
            'recoveryFactor': self.specification['recoveryFactor'],
            'limitations': ['토성 문헌값·초기 부족률은 현장 관측 함수율이 아님',
                '부분 투수 영역은 삼각형 수심 공유 근사',
                'EPA 회복식 상태이며 토양층·지하수·증발산 전체 물수지 아님']}
        if include_state:
            result.update(triangles=self.indices.tolist(), infiltrationByTriangleM3=self.cumulative.tolist(),
                nativeStateFields=['IMD', 'F_ft', 'Fu_ft', 'Sat', 'T_seconds'],
                nativeState=self.bank.state().tolist() if self.bank else [])
        if self.specification['schemaVersion'] == 2:
            result.update(schemaVersion=2, partitionPolicy='EXPLICIT_AREA_FRACTIONS',
                          sharedPonding=True, infiltrationRoundoffM3=self.roundoff_m3)
            if include_state:
                result.pop('infiltrationByTriangleM3')
                result.update(perviousFractions=self.fractions.tolist(),
                    infiltrationByPatchM3=self.cumulative.tolist(),
                    triangleTotals=[{'triangle': int(cell), 'infiltrationM3': float(volume)}
                        for cell, volume in zip(self.cells, self.np.bincount(self.cell_inverse,
                            weights=self.cumulative, minlength=len(self.cells)))])
        return result

    def statistics(self):
        return 'EPA 지표 침투'

    timestepping_statistics = statistics

    def log_timestepping_statistics(self):
        return None
