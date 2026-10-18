"""명시된 삼각 격자와 경계 조건을 사용하는 ANUGA 지표 흐름 어댑터."""
import hashlib
from bisect import bisect_left, bisect_right
from importlib import metadata
import json
import math
from pathlib import Path
import platform

from waterleague_sim.engine.flood_errors import require
from waterleague_sim.engine.swmm import ROOT
from waterleague_sim.forcing.stage import clamp_clock_roundoff, compile_stage_boundaries, source_hash

VERSION = '4.0.1'


def identity():
    try:
        distribution = metadata.distribution('anuga')
    except metadata.PackageNotFoundError:
        require(False, 'SURFACE_ENGINE_REQUIRED')
    require(distribution.version == VERSION, 'SURFACE_ENGINE_VERSION_MISMATCH')
    files = {}
    for item in sorted(distribution.files or []):
        if str(item).startswith('anuga/') and item.suffix in ('.py', '.so', '.pyd', '.dylib'):
            files[str(item)] = hashlib.sha256(distribution.locate_file(item).read_bytes()).hexdigest()
    require(files, 'SURFACE_ENGINE_IDENTITY_INVALID')
    return {'name': 'ANUGA', 'version': VERSION, 'platform': platform.platform(),
            'python': platform.python_version(), 'installedCodeSha256': hashlib.sha256(
                json.dumps(files, sort_keys=True).encode()).hexdigest(),
            'binarySha256': {name: digest for name, digest in files.items() if not name.endswith('.py')},
            'adapterSha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'dependencyLockSha256': hashlib.sha256((ROOT / 'simulation/uv.lock').read_bytes()).hexdigest(),
            'sourceManifestSha256': hashlib.sha256((ROOT / 'data/manifests/anuga-4.0.1.json').read_bytes()).hexdigest(),
            'runtimePackages': {name: metadata.version(name) for name in
                                ('numpy', 'scipy', 'netCDF4', 'pyproj')}}


class SurfaceSession:
    def __init__(self, model, directory):
        self.engine = identity()
        import numpy as np
        import anuga
        self.np = np
        self.gravity_mps2 = anuga.g
        require(type(model.get('schemaVersion')) is int and model['schemaVersion'] in (1, 2)
                and model.get('coordinateSystem')
                and model.get('verticalDatum') and model.get('evidence'), 'SURFACE_REFERENCE_REQUIRED')
        max_step = model.get('maxStepSeconds')
        require(type(max_step) in (float, int) and math.isfinite(max_step) and 0 < max_step <= 60,
                'SURFACE_MAX_STEP_REQUIRED')
        try:
            points = np.asarray(model['verticesM'], dtype=float)
            triangles = np.asarray(model['triangles'])
            elevations = np.asarray(model['elevationM'], dtype=float)
            depths = np.asarray(model['initialDepthM'], dtype=float)
            roughness = np.asarray(model['manningN'], dtype=float)
            owners = np.asarray(model['rainfallOwner'])
        except (KeyError, TypeError, ValueError):
            require(False, 'SURFACE_MESH_INVALID')
        require(points.ndim == 2 and points.shape[1] == 2 and 3 <= len(points) <= 500_000
                and triangles.ndim == 2 and triangles.shape[1] == 3
                and 1 <= len(triangles) <= 200_000 and np.issubdtype(triangles.dtype, np.integer)
                and np.all(triangles >= 0) and np.all(triangles < len(points)), 'SURFACE_MESH_INVALID')
        require(elevations.shape == (len(points),) and depths.shape == roughness.shape == owners.shape
                == (len(triangles),) and all(np.all(np.isfinite(a)) for a in
                    (points, elevations, depths, roughness))
                and np.all(depths >= 0) and np.all(roughness >= 0)
                and np.all(np.isin(owners, ('SURFACE', 'NETWORK'))), 'SURFACE_FIELDS_INVALID')
        a = points[triangles[:, 1]] - points[triangles[:, 0]]
        b = points[triangles[:, 2]] - points[triangles[:, 0]]
        require(np.all(a[:, 0] * b[:, 1] - a[:, 1] * b[:, 0] > 0)
                and len(np.unique(np.sort(triangles, axis=1), axis=0)) == len(triangles),
                'SURFACE_TRIANGLE_INVALID')
        # 모든 외곽 변의 경계를 요구하여 누락된 방류구를 벽으로 대체하지 않는다.
        edges, boundaries = {}, {}
        for i, triangle in enumerate(triangles):
            for k in range(3):
                edge = tuple(sorted((int(triangle[(k+1) % 3]), int(triangle[(k+2) % 3]))))
                edges.setdefault(edge, []).append((i, k))
        require(all(len(rows) <= 2 for rows in edges.values()), 'SURFACE_NONMANIFOLD_MESH')
        expected = {rows[0] for rows in edges.values() if len(rows) == 1}
        specifications = model.get('boundaryConditions', {})
        for row in model.get('boundaryEdges', []):
            require(isinstance(row, list) and len(row) == 3 and type(row[0]) is int
                    and type(row[1]) is int and (row[0], row[1]) in expected
                    and row[2] in specifications and (row[0], row[1]) not in boundaries,
                    'SURFACE_BOUNDARY_INVALID')
            boundaries[row[0], row[1]] = row[2]
        require(set(boundaries) == expected, 'SURFACE_BOUNDARY_INCOMPLETE')
        self.stage_series = compile_stage_boundaries(model)
        self.stage_knots = sorted({time for series in self.stage_series.values() for time in series.knots})
        if self.stage_series:
            require(set(self.stage_series) <= set(boundaries.values()), 'STAGE_BOUNDARY_UNUSED')
            self.engine['stageAdapterSha256'] = source_hash()
        path = Path(directory).resolve()
        require(not path.exists(), 'SURFACE_OUTPUT_EXISTS')
        path.mkdir(parents=True)
        self.directory = path
        (path / 'surface-input.json').write_text(json.dumps(model, allow_nan=False) + '\n')
        anuga.set_omp_num_threads(1, verbose=False)
        self.domain = domain = anuga.Domain(points, triangles, boundaries, verbose=False,
                                           use_inscribed_circle=model['schemaVersion'] == 2)
        domain.set_compute_mode('legacy')
        domain.set_flow_algorithm('DE0')
        # 건조 격자의 초기 CFL만으로 큰 단계를 택하면 강우가 마지막에 한꺼번에 들어간다.
        domain.set_evolve_max_timestep(max_step)
        domain.set_quantity('elevation', elevations[triangles], location='vertices')
        domain.set_quantity('friction', roughness, location='centroids')
        domain.set_quantity('stage', domain.quantities['elevation'].centroid_values + depths,
                            location='centroids')
        boundary_objects = {}
        for name in set(boundaries.values()):
            spec = specifications[name]
            if spec == {'type': 'REFLECTIVE'}:
                boundary_objects[name] = anuga.Reflective_boundary(domain)
            elif spec == {'type': 'TRANSMISSIVE'}:
                boundary_objects[name] = anuga.Transmissive_boundary(domain)
            elif spec.get('type') == 'FIXED_STAGE':
                require(type(spec.get('stageM')) in (float, int) and math.isfinite(spec['stageM']),
                        'SURFACE_BOUNDARY_INVALID')
                boundary_objects[name] = anuga.Dirichlet_boundary([spec['stageM'], 0, 0])
            elif name in self.stage_series:
                boundary_objects[name] = anuga.Time_boundary(domain, function=self.stage_series[name])
            else:
                require(False, 'SURFACE_BOUNDARY_UNSUPPORTED')
        domain.set_boundary(boundary_objects)
        domain.set_datadir(str(path))
        domain.set_name('surface')
        domain.set_store(True)
        domain.set_store_centroids(True)
        self.numerics = {'policyVersion': ('ANUGA_DE0_INSCRIBED_RADIUS_v2' if model['schemaVersion'] == 2
                         else 'ANUGA_DE0_LEGACY_RADIUS_v1'),
            'meshRadiusMethod': ('INSCRIBED_CIRCLE_2_AREA_OVER_PERIMETER' if domain.mesh.use_inscribed_circle
                                 else 'CENTROID_TO_NEAREST_EDGE_MIDPOINT'),
            'minimumRadiusM': float(np.min(domain.radii)), 'maximumRadiusM': float(np.max(domain.radii)),
            'cfl': float(domain.get_cfl()), 'configuredMaximumStepSeconds': max_step,
            'algorithm': domain.get_algorithm_parameters()}
        (path / 'surface-numerics.json').write_text(json.dumps(self.numerics, allow_nan=False, indent=2) + '\n')
        if self.stage_series:
            (path / 'surface-stage-boundaries.json').write_text(json.dumps(
                {name: series.summary for name, series in self.stage_series.items()},
                ensure_ascii=False, allow_nan=False, indent=2) + '\n')
        self.owners = owners
        self.station_indices = None
        if model.get('rainfallStationIds') is not None:
            assignments = model['rainfallStationIds']
            require(isinstance(assignments, list) and len(assignments) == len(owners)
                    and all((owner == 'NETWORK' and sid is None) or
                        (owner == 'SURFACE' and isinstance(sid, str) and sid.isdigit())
                        for owner, sid in zip(owners, assignments)), 'SURFACE_STATION_ASSIGNMENT_INVALID')
            self.station_indices = {sid: np.asarray([i for i, value in enumerate(assignments) if value == sid])
                                    for sid in sorted({sid for sid in assignments if sid is not None})}
        self.forcing = []
        self.rain = anuga.Rate_operator(domain, rate=np.zeros(len(triangles)), factor=1 / 3_600_000)
        self.metrics = None
        if model.get('evaluationMetrics') is not None:
            from waterleague_sim.engine.flood_metrics import DepthMetrics
            self.metrics = DepthMetrics(domain, model['evaluationMetrics'])
        self.initial_volume = float(np.dot(depths, domain.areas))
        self.quality = None
        if model['schemaVersion'] == 2:
            from waterleague_sim.engine.surface_quality import SurfaceQuality
            self.quality = SurfaceQuality(domain, self.initial_volume, path)
            self.engine['qualityAdapterSha256'] = self.quality.source_hash
        self.finished = False
        self.initial = self.snapshot()

    def set_rainfall(self, rates_mm_hour):
        require(not self.finished, 'SURFACE_SESSION_FINISHED')
        require(self.station_indices is None, 'SURFACE_RAINFALL_BINDING_REQUIRED')
        np = self.np
        rates = np.asarray(rates_mm_hour, dtype=float)
        require(rates.shape == self.owners.shape and np.all(np.isfinite(rates))
                and np.all(rates >= 0), 'SURFACE_RAINFALL_INVALID')
        require(np.all(rates[self.owners != 'SURFACE'] == 0), 'SURFACE_RAINFALL_DOUBLE_COUNT')
        self.rain.set_rate(rates.copy())
        self.forcing.append({'timeSeconds': self.domain.get_time(), 'ratesMmH': rates.tolist()})

    def set_station_rainfall(self, rates_by_station):
        require(not self.finished, 'SURFACE_SESSION_FINISHED')
        require(self.station_indices is not None and isinstance(rates_by_station, dict)
                and set(rates_by_station) == set(self.station_indices)
                and all(type(rate) in (int, float) and math.isfinite(rate) and rate >= 0
                        for rate in rates_by_station.values()), 'SURFACE_STATION_RAINFALL_INVALID')
        rates = self.np.zeros(len(self.owners))
        for sid, indices in self.station_indices.items():
            rates[indices] = rates_by_station[sid]
        self.rain.set_rate(rates)
        self.forcing.append({'timeSeconds': self.domain.get_time(),
                             'ratesMmHByStation': dict(rates_by_station)})

    def snapshot(self):
        np, domain = self.np, self.domain
        z = domain.quantities['elevation'].centroid_values
        stage = domain.quantities['stage'].centroid_values
        depth = stage - z
        momenta = [domain.quantities[k].centroid_values for k in ('xmomentum', 'ymomentum')]
        require(all(np.all(np.isfinite(a)) for a in (depth, *momenta))
                and np.min(depth) >= -1e-10, 'SURFACE_NONPHYSICAL_RESULT')
        velocities = [np.divide(a, depth, out=np.zeros_like(depth), where=depth > 1e-6)
                      for a in momenta]
        volume = float(np.dot(depth, domain.areas))
        boundary = float(domain.get_boundary_flux_integral())
        forcing = float(domain.get_fractional_step_volume_integral())
        return {'timeSeconds': float(domain.get_time()), 'storageM3': volume,
                'boundaryNetInflowM3': boundary, 'sourceNetInflowM3': forcing,
                'balanceResidualM3': self.initial_volume + boundary + forcing - volume,
                'depthM': depth.tolist(), 'velocityXMps': velocities[0].tolist(),
                'velocityYMps': velocities[1].tolist()}

    def advance(self, seconds):
        require(not self.finished and type(seconds) in (int, float)
                and math.isfinite(seconds) and 0 < seconds <= 3600, 'SURFACE_STEP_INVALID')
        target = self.domain.get_time() + seconds
        self._evolve_until(target)
        require(math.isclose(self.domain.get_time(), target, abs_tol=1e-9), 'SURFACE_TIME_MISMATCH')
        return self.snapshot()

    def _evolve_until(self, target):
        if self.stage_series:
            target = clamp_clock_roundoff(target, 0, min(s.duration for s in self.stage_series.values()),
                                           'STAGE_RUN_WINDOW_EXCEEDED')
        # 관측 절점의 기울기 변화가 긴 내부 단계에 묻히지 않도록 분할한다.
        begin = bisect_right(self.stage_knots, self.domain.get_time())
        end = bisect_left(self.stage_knots, target)
        stops = self.stage_knots[begin:end] + [target]
        for stop in stops:
            for _ in self.domain.evolve(yieldstep=stop - self.domain.get_time(), finaltime=stop,
                                       skip_initial_step=True):
                pass

    def finish(self):
        require(not self.finished, 'SURFACE_SESSION_FINISHED')
        final = self.snapshot()
        self.finished = True
        if self.quality is not None:
            self.quality.observe(float(self.domain.get_time()))
            self.quality.save()
        # 수심/운동량은 그대로 보존하며 초기 수치 시험의 잔차 허용치만 별도 판정한다.
        scale = max(self.initial_volume + max(0, final['sourceNetInflowM3'])
                    + max(0, final['boundaryNetInflowM3']), final['storageM3'])
        result = {'schemaVersion': 1, 'engine': self.engine, 'algorithm': self.domain.get_algorithm_parameters(),
                  'numericalConfiguration': self.numerics,
                  'computeMode': self.domain.compute_mode, 'threads': 1,
                  'gravityMps2': self.gravity_mps2,
                  'maximumStepSeconds': self.domain.get_evolve_max_timestep(),
                  'initial': self.initial, 'final': final, 'forcing': self.forcing,
                  'numericalStatus': 'PASSED' if abs(final['balanceResidualM3']) <= max(1e-8, .01 * scale)
                      else 'FAILED',
                  'files': {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                            for p in sorted(self.directory.iterdir()) if p.is_file()}}
        if self.metrics is not None:
            result['evaluationMetrics'] = self.metrics.snapshot()
        if self.stage_series:
            result['stageBoundaries'] = {name: series.summary for name, series in self.stage_series.items()}
        if self.quality is not None:
            result['numericalQuality'] = self.quality.snapshot()
        (self.directory / 'surface-result.json').write_text(json.dumps(result, allow_nan=False, indent=2) + '\n')
        return result
