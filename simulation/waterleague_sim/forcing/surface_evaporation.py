"""명시된 시각 구간의 기준 증발산과 지표 계산 시계 연결."""
from bisect import bisect_right
from copy import deepcopy
from datetime import timedelta
import hashlib
import json
from pathlib import Path

from waterleague_sim.engine.flood_errors import require
from waterleague_sim.engine.swmm import ROOT
from waterleague_sim.forcing.reference_evaporation import read_reference
from waterleague_sim.forcing.stage import utc, finite, clamp_clock_roundoff, require_network_start
from waterleague_sim.ingestion.evaporation import METHOD

TRANSFER = 'REFERENCE_GRASS_ET_AS_PONDED_WATER_POTENTIAL_UNCALIBRATED'


def source_hash():
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


class EvaporationSeries:
    def __init__(self, specification, model, *, root=ROOT):
        specification = deepcopy(specification)
        require(isinstance(specification, dict) and specification.get('schemaVersion') == 1
                and specification.get('ownershipPolicy') == 'SURFACE_ONLY'
                and specification.get('surfaceTransfer') == TRANSFER
                and specification.get('evidence'), 'EVAPORATION_SPECIFICATION_INVALID')
        self.start = utc(model.get('startUtc'))
        self.duration = model.get('durationSeconds')
        require(finite(self.duration) and 0 < self.duration <= 366 * 86400
                and float(self.duration * 1000).is_integer(), 'EVAPORATION_DURATION_INVALID')
        self.files = {}
        kind = specification.get('type')
        if kind in ('ARCHIVED_FAO56', 'ARCHIVED_ANTECEDENT_AND_FAO56'):
            data, self.files, code = read_reference(specification.get('reference'), root)
            require((kind != 'ARCHIVED_FAO56' or utc(data['start']) <= self.start)
                    and utc(data['end']) >= self.start + timedelta(seconds=self.duration),
                    'EVAPORATION_COVERAGE_INCOMPLETE')
            if data['method'] == METHOD:
                intervals = [{'startUtc': row['appliesFrom'], 'endUtc': row['appliesUntil'],
                              'rateMmDay': row['referenceEtMmHour'] * 24} for row in data['hours']]
                maximum_interval = 3600
            else:
                intervals = [{'startUtc': data['start'], 'endUtc': data['end'],
                              'rateMmDay': data['ratesMmDay'][0]}]
                maximum_interval = 86400
            self.summary = {key: data[key] for key in ('method', 'timePolicy', 'evidence', 'station', 'assumptions')}
            self.summary.update(reference=specification['reference'], reconstructionImplementationHashes=code,
                referenceAdapterSha256=hashlib.sha256(Path(__file__).with_name('reference_evaporation.py').read_bytes()).hexdigest())
            if kind == 'ARCHIVED_ANTECEDENT_AND_FAO56':
                from waterleague_sim.forcing.antecedent_archive import read_antecedent
                rain, prior, files, summary = read_antecedent(specification.get('antecedentReference'), root)
                require(utc(rain['start']) <= self.start < utc(rain['end']) == utc(data['start']),
                        'EVAPORATION_ANTECEDENT_BINDING_INVALID')
                split = utc(data['start'])
                # 평가 기상 파일의 범위 밖 선행 구간만 이전 완료 일 자료로 채운다.
                evaluation = [row | {'startUtc': max(utc(row['startUtc']), split).isoformat()}
                              for row in intervals if utc(row['endUtc']) > split]
                intervals = [{'startUtc': row['start'], 'endUtc': row['end'],
                              'rateMmDay': row['ratesMmDay'][0]} for row in prior['segments']] + evaluation
                maximum_interval = 86400
                self.files.update(files)
                self.summary.update(antecedent=summary, timePolicy='LAGGED_DAILY_ANTECEDENT_THEN_DECLARED_EVALUATION',
                    antecedentTimePolicy='PREVIOUS_COMPLETED_DAY_HELD_OVER_NEXT_DAY',
                    evaluationTimePolicy=data['timePolicy'])
        else:
            require(kind == 'NUMERICAL_TEST_SERIES' and
                    model.get('evidence') in ('ANALYTICAL_TEST_ONLY', 'NUMERICAL_TEST_ONLY_NOT_SEOUL'),
                    'EVAPORATION_SOURCE_KIND_INVALID')
            intervals = specification.get('intervals')
            maximum_interval = specification.get('maximumIntervalSeconds')
            self.summary = {'method': kind, 'timePolicy': 'EXPLICIT_NUMERICAL_TEST_INTERVALS',
                            'evidence': specification['evidence'], 'assumptions': ['해석 검사 전용 비관측 입력']}
        require(finite(maximum_interval) and 0 < maximum_interval <= 86400
                and isinstance(intervals, list) and 1 <= len(intervals) <= 100_000,
                'EVAPORATION_INTERVALS_INVALID')
        self.intervals, previous = [], None
        for row in intervals:
            require(isinstance(row, dict) and finite(row.get('rateMmDay')) and 0 <= row['rateMmDay'] <= 100,
                    'EVAPORATION_RATE_INVALID')
            begin, end = utc(row.get('startUtc')), utc(row.get('endUtc'))
            require(0 < (end - begin).total_seconds() <= maximum_interval
                    and (previous is None or previous == begin), 'EVAPORATION_GAP_OR_OVERLAP')
            previous = end
            a, b = (begin - self.start).total_seconds(), (end - self.start).total_seconds()
            require(float(a * 1000).is_integer() and float(b * 1000).is_integer(),
                    'EVAPORATION_TIME_PRECISION_INVALID')
            if b > 0 and a < self.duration:
                self.intervals.append((max(0., a), min(self.duration, b), float(row['rateMmDay'])))
        require(self.intervals and self.intervals[0][0] == 0 and self.intervals[-1][1] == self.duration,
                'EVAPORATION_COVERAGE_INCOMPLETE')
        self.starts = [row[0] for row in self.intervals]
        self.knots = self.starts[1:]
        self.summary.update(startUtc=self.start.isoformat(), durationSeconds=self.duration,
            interpolation='CONSTANT_WITHIN_DECLARED_INTERVAL', extrapolation='FORBIDDEN',
            intervalCount=len(self.intervals), maximumIntervalSeconds=maximum_interval,
            potentialDepthMm=sum(rate * (b-a) / 86400 for a, b, rate in self.intervals),
            ownershipPolicy='SURFACE_ONLY', surfaceTransfer=TRANSFER, assignmentEvidence=specification['evidence'],
            sourceFiles={name: hashlib.sha256(raw).hexdigest() for name, raw in self.files.items()},
            adapterSha256=source_hash(), rankingEligible=False)

    def step_depth_m(self, start, duration):
        require(finite(start) and finite(duration) and duration > 0, 'EVAPORATION_STEP_INVALID')
        start = clamp_clock_roundoff(start, 0, self.duration, 'EVAPORATION_RUN_WINDOW_EXCEEDED')
        require(start < self.duration, 'EVAPORATION_RUN_WINDOW_EXCEEDED')
        a, b, rate = self.intervals[bisect_right(self.starts, start) - 1]
        end = clamp_clock_roundoff(start + duration, a, b, 'EVAPORATION_INTERVAL_STRADDLED')
        return rate * (end - start) / 86_400_000

    def archive(self, directory):
        directory.mkdir(parents=True)
        for relative, raw in self.files.items():
            path = directory / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        (directory / 'forcing-summary.json').write_text(
            json.dumps(self.summary, ensure_ascii=False, allow_nan=False, indent=2) + '\n')


def compile_evaporation(model):
    return EvaporationSeries(model['evaporation'], model) if model.get('evaporation') is not None else None


def require_evaporation_clock(model, *, duration, rainfall=None, network=None):
    series = compile_evaporation(model)
    if series is not None:
        require(series.duration == duration, 'EVAPORATION_DURATION_MISMATCH')
        if rainfall is not None:
            require(series.start == utc(rainfall.get('startUtc')) and
                    (utc(rainfall.get('endUtc')) - series.start).total_seconds() == duration,
                    'EVAPORATION_RAIN_CLOCK_MISMATCH')
        if network is not None:
            require_network_start(network, series.start)
    return series
