"""보관 AWS 풍향·풍속의 시계, 높이 및 방향 변환 계약."""
from bisect import bisect_right
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path

from waterleague_sim.engine.flood_errors import FloodModelError, require
from waterleague_sim.engine.swmm import ROOT
from waterleague_sim.forcing.reference_evaporation import read_reference
from waterleague_sim.forcing.stage import utc, finite, clamp_clock_roundoff, require_network_start
from waterleague_sim.ingestion.live import ENDPOINT, KST

HEC = 'https://www.hec.usace.army.mil/confluence/rasdocs/ras1dtechref/6.6/theoretical-basis-for-one-dimensional-and-two-dimensional-hydrodynamic-calculations/2d-unsteady-flow-hydrodynamics/hydraulic-equations/wind-surface-stress'
HEIGHT = 'https://www.hec.usace.army.mil/software/hec-ras/documentation/HEC-RAS_6.0_ReferenceManual.pdf'
POLICY = 'KMA_WIND_TO_ANUGA_SI_RELATIVE_V1'


def source_hash():
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def aws_rows(raw):
    """무풍 코드 360을 북풍으로 오인하지 않으며 결측은 보간하지 않는다."""
    try:
        text = raw.decode('utf-8')
        require(text.startswith('#START7777') and text.strip().endswith('#7777END')
                and '#  WD1' in text and '#  WS1' in text and '360-무풍' in text,
                'WIND_AWS_FORMAT_INVALID')
        result = {}
        for line in text.splitlines():
            if not line.strip() or line.startswith('#'):
                continue
            fields = line.split()
            require(len(fields) == 18 and fields[1] == '108', 'WIND_AWS_STATION_INVALID')
            at = datetime.strptime(fields[0], '%Y%m%d%H%M').replace(tzinfo=KST).astimezone(timezone.utc)
            direction, speed = map(float, fields[2:4])
            require(at not in result and math.isfinite(speed) and 0 <= speed <= 150
                    and math.isfinite(direction), 'WIND_OBSERVATION_INVALID')
            require(speed == 0 or 0 <= direction < 360, 'WIND_DIRECTION_MISSING_OR_CALM_CONFLICT')
            require(speed != 0 or direction in (-99., -999., 360.) or 0 <= direction < 360,
                    'WIND_CALM_DIRECTION_INVALID')
            result[at] = (speed, None if speed == 0 else direction)
        require(result, 'WIND_OBSERVATIONS_REQUIRED')
        return result
    except FloodModelError:
        raise
    except (ValueError, UnicodeError):
        raise FloodModelError('WIND_AWS_FORMAT_INVALID') from None


class WindSeries:
    def __init__(self, specification, model, *, root=ROOT):
        spec = deepcopy(specification)
        require(isinstance(spec, dict) and type(spec.get('schemaVersion')) is int
                and spec['schemaVersion'] == 1 and spec.get('policyVersion') == POLICY
                and spec.get('evidence') and spec.get('densityEvidence'), 'WIND_SPECIFICATION_INVALID')
        self.start, self.duration = utc(model.get('startUtc')), model.get('durationSeconds')
        require(finite(self.duration) and 0 < self.duration <= 366*86400
                and float(self.duration*1000).is_integer(), 'WIND_DURATION_INVALID')
        self.air_density, self.water_density = spec.get('airDensityKgM3'), spec.get('waterDensityKgM3')
        require(finite(self.air_density) and .5 <= self.air_density <= 2
                and finite(self.water_density) and 990 <= self.water_density <= 1030,
                'WIND_SI_DENSITY_REQUIRED')
        self.integration = spec.get('integrationPolicy')
        require(self.integration in ('ANUGA_EXPLICIT_DIAGNOSTIC_V1', 'FROZEN_DRAG_EXACT_RELATIVE_V1'),
                'WIND_INTEGRATION_POLICY_REQUIRED')
        self.drag_law = spec.get('dragLaw')
        self.constant_drag = spec.get('constantDragCoefficient')
        self.files = {}
        kind = spec.get('type')
        self.summary = {'policyVersion': POLICY, 'type': kind, 'references': [HEC, HEIGHT],
            'densityEvidence': spec['densityEvidence'], 'assignmentEvidence': spec['evidence']}
        if kind == 'ARCHIVED_KMA_AWS':
            require(self.drag_law == 'GARRATT_HEC_6_6' and self.constant_drag is None
                    and self.integration == 'FROZEN_DRAG_EXACT_RELATIVE_V1',
                    'WIND_OBSERVED_DRAG_POLICY_INVALID')
            data, self.files, _ = read_reference(spec.get('reference'), root)
            rows = {}
            for request in data['sourceRequests']:
                if request['endpoint'] == ENDPOINT:
                    chunk = aws_rows(self.files[request['rawFile']])
                    require(not rows.keys() & chunk.keys(), 'WIND_OBSERVATION_OVERLAP')
                    rows.update(chunk)
            require(rows, 'WIND_MINUTE_OBSERVATIONS_REQUIRED')
            station = data['station']
            height = station['windHeightM']
            intervals = [{'startUtc': at.isoformat(), 'endUtc': (at+timedelta(minutes=1)).isoformat(),
                          'speedMs': speed, 'fromDegrees': direction}
                         for at, (speed, direction) in sorted(rows.items())]
            self.summary.update(station=station, reference=spec['reference'],
                timePolicy='COMPLETED_ONE_MINUTE_MEAN_HELD_OVER_NEXT_MINUTE',
                observationFields=['WD1', 'WS1'], measuredHeightReference='ABOVE_STATION_GROUND',
                spatialTransfer='SINGLE_STATION_UNIFORM_WIND_UNCALIBRATED')
        else:
            require(kind == 'NUMERICAL_TEST_SERIES' and model.get('evidence') in
                    ('ANALYTICAL_TEST_ONLY', 'NUMERICAL_TEST_ONLY_NOT_SEOUL'), 'WIND_SOURCE_KIND_INVALID')
            require(self.drag_law in ('GARRATT_HEC_6_6', 'CONSTANT_NUMERICAL_ONLY'), 'WIND_DRAG_INVALID')
            if self.drag_law == 'CONSTANT_NUMERICAL_ONLY':
                require(finite(self.constant_drag) and 0 < self.constant_drag <= .01, 'WIND_DRAG_INVALID')
            height, intervals = spec.get('measurementHeightM'), spec.get('intervals')
            self.summary.update(timePolicy='EXPLICIT_NUMERICAL_TEST_INTERVALS',
                                spatialTransfer='SYNTHETIC_UNIFORM_TRUE_EAST_NORTH')
        require(finite(height) and .1 <= height <= 100
                and spec.get('heightCorrection') == 'POWER_LAW_ONE_SEVENTH_UNCALIBRATED',
                'WIND_HEIGHT_POLICY_REQUIRED')
        self.height_factor = (10 / height)**(1/7)
        require(isinstance(intervals, list) and 1 <= len(intervals) <= 100_000,
                'WIND_INTERVALS_INVALID')
        self.intervals, previous = [], None
        for row in intervals:
            require(isinstance(row, dict) and finite(row.get('speedMs')) and 0 <= row['speedMs'] <= 150,
                    'WIND_SPEED_INVALID')
            speed, direction = row['speedMs'], row.get('fromDegrees')
            require((speed == 0 and (direction is None or finite(direction) and 0 <= direction <= 360))
                    or (speed > 0 and finite(direction) and 0 <= direction < 360), 'WIND_DIRECTION_INVALID')
            begin, end = utc(row.get('startUtc')), utc(row.get('endUtc'))
            require(0 < (end-begin).total_seconds() <= 60 and (previous is None or previous == begin),
                    'WIND_GAP_OR_OVERLAP')
            previous = end
            a, b = (begin-self.start).total_seconds(), (end-self.start).total_seconds()
            require(float(a*1000).is_integer() and float(b*1000).is_integer(), 'WIND_TIME_PRECISION_INVALID')
            if b > 0 and a < self.duration:
                radians = math.radians(direction or 0)
                # 기상 풍향은 불어오는 방향이므로 물을 미는 방향으로 반전한다.
                u, v = -speed*self.height_factor*math.sin(radians), -speed*self.height_factor*math.cos(radians)
                self.intervals.append((max(0., a), min(self.duration, b), u, v))
        require(self.intervals and self.intervals[0][0] == 0 and self.intervals[-1][1] == self.duration,
                'WIND_COVERAGE_INCOMPLETE')
        self.starts = [row[0] for row in self.intervals]
        self.knots = self.starts[1:]
        self.basis = spec.get('vectorBasis')
        require(self.basis in ('PROJECTED_TRUE_NORTH_WGS84', 'LOCAL_TRUE_EAST_NORTH_DIAGNOSTIC'),
                'WIND_VECTOR_BASIS_REQUIRED')
        if self.basis == 'LOCAL_TRUE_EAST_NORTH_DIAGNOSTIC':
            require(model.get('coordinateSystem') == 'LOCAL_REFERENCE_METRES' and 'terrainProvenance' not in model,
                    'WIND_LOCAL_BASIS_NOT_GEOGRAPHIC')
        else:
            require(model.get('coordinateSystem') == 'EPSG:5186', 'WIND_PROJECTED_CRS_UNSUPPORTED')
        self.summary.update(startUtc=self.start.isoformat(), durationSeconds=self.duration,
            intervalCount=len(self.intervals), measuredHeightM=height, referenceHeightM=10.,
            heightCorrection=spec['heightCorrection'], speedHeightFactor=self.height_factor,
            airDensityKgM3=self.air_density, waterDensityKgM3=self.water_density,
            dragLaw=self.drag_law, constantDragCoefficient=self.constant_drag, integrationPolicy=self.integration,
            velocityReference='WIND_RELATIVE_TO_DEPTH_AVERAGED_WATER', vectorBasis=self.basis,
            interpolation='CONSTANT_WITHIN_DECLARED_INTERVAL', extrapolation='FORBIDDEN',
            sourceFiles={name: hashlib.sha256(raw).hexdigest() for name, raw in self.files.items()},
            adapterSha256=source_hash(), rankingEligible=False,
            limitations=['풍속계 지상 높이를 수면 위 높이에 대응시킨 1/7 환산 가정; 도시 차폐·안정도 미보정',
                '단일 관측소의 공간 대표성·수면 국소 바람 미검증',
                '해상 경험 항력식의 얕은 도시 침수 전용 미검증; 물결·풍파·비산수 미포함',
                '공기·물 밀도는 명시한 고정 SI 가정이며 현장 측정값 아님'])

    def vector(self, start, duration):
        require(finite(duration) and duration > 0, 'WIND_STEP_INVALID')
        start = clamp_clock_roundoff(start, 0, self.duration, 'WIND_RUN_WINDOW_EXCEEDED')
        require(start < self.duration, 'WIND_RUN_WINDOW_EXCEEDED')
        a, b, u, v = self.intervals[bisect_right(self.starts, start)-1]
        clamp_clock_roundoff(start+duration, a, b, 'WIND_INTERVAL_STRADDLED')
        return u, v

    def archive(self, directory):
        directory.mkdir(parents=True)
        for relative, raw in self.files.items():
            path = directory / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        (directory / 'forcing-summary.json').write_text(json.dumps(
            self.summary, ensure_ascii=False, allow_nan=False, indent=2)+'\n')


def compile_wind(model):
    return WindSeries(model['wind'], model) if model.get('wind') is not None else None


def require_wind_clock(model, *, duration, rainfall=None, network=None):
    series = compile_wind(model)
    if series is not None:
        require(series.duration == duration, 'WIND_DURATION_MISMATCH')
        if rainfall is not None:
            require(series.start == utc(rainfall.get('startUtc')) and
                    (utc(rainfall.get('endUtc'))-series.start).total_seconds() == duration,
                    'WIND_RAIN_CLOCK_MISMATCH')
        if network is not None:
            require_network_start(network, series.start)
    return series
