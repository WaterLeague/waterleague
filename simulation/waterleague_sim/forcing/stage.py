"""관측 절점을 벗어나지 않는 경계수위와 계산 시각 계약."""
from bisect import bisect_right
from datetime import datetime, timezone
import hashlib
import math
from pathlib import Path
import re

from waterleague_sim.engine.flood_errors import FloodModelError, require


def utc(value):
    try:
        instant = datetime.fromisoformat(value)
        require(instant.utcoffset() is not None, 'STAGE_TIME_INVALID')
        return instant.astimezone(timezone.utc)
    except (TypeError, ValueError):
        raise FloodModelError('STAGE_TIME_INVALID') from None


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def clamp_clock_roundoff(value, lower, upper, code):
    require(finite(value), code)
    if value < lower and lower - value <= 8 * max(math.ulp(value), math.ulp(lower)):
        value = lower
    if value > upper and value - upper <= 8 * max(math.ulp(value), math.ulp(upper)):
        value = upper
    require(lower <= value <= upper, code)
    return value


class StageSeries:
    def __init__(self, specification, model, *, momentum_policy='ZERO_RESERVOIR_ASSUMPTION'):
        require(momentum_policy in ('ZERO_RESERVOIR_ASSUMPTION', 'SWMM_DYNAMIC_WAVE'),
                'STAGE_MOMENTUM_POLICY_INVALID')
        require(specification.get('type') == 'TIME_SERIES_STAGE'
                and specification.get('unit') == 'm'
                and specification.get('interpolation') == 'LINEAR'
                and specification.get('momentum') == momentum_policy
                and specification.get('evidence'), 'STAGE_SPECIFICATION_INVALID')
        require(specification.get('verticalDatum') == model.get('verticalDatum')
                and bool(model.get('verticalDatum')), 'STAGE_DATUM_MISMATCH')
        reference = specification.get('referenceStatus')
        require(reference in ('VERIFIED_ABSOLUTE', 'LOCAL_DIAGNOSTIC'), 'STAGE_REFERENCE_INVALID')
        if 'terrainProvenance' in model:
            require(reference == 'VERIFIED_ABSOLUTE' and
                    model['terrainProvenance'].get('absoluteVerticalReferenceVerified') is True,
                    'STAGE_TERRAIN_DATUM_UNVERIFIED')
        self.start = utc(model.get('startUtc'))
        self.duration = model.get('durationSeconds')
        require(finite(self.duration) and 0 < self.duration <= 366 * 86400
                and float(self.duration * 1000).is_integer(), 'STAGE_DURATION_INVALID')
        if reference == 'VERIFIED_ABSOLUTE':
            proof = specification.get('datumEvidence', {})
            require(isinstance(proof, dict) and proof.get('verticalDatum') == model['verticalDatum']
                    and isinstance(proof.get('sourceSha256'), str)
                    and re.fullmatch(r'[a-f0-9]{64}', proof['sourceSha256']), 'STAGE_DATUM_EVIDENCE_REQUIRED')
            require(utc(proof.get('validFromUtc')) <= self.start and
                    (utc(proof.get('validUntilUtc')) - self.start).total_seconds() >= self.duration,
                    'STAGE_DATUM_PERIOD_MISMATCH')
        maximum_gap = specification.get('maximumGapSeconds')
        require(finite(maximum_gap) and 0 < maximum_gap <= 86400, 'STAGE_GAP_POLICY_INVALID')
        samples = specification.get('samples')
        require(isinstance(samples, list) and 2 <= len(samples) <= 100_000, 'STAGE_SAMPLES_INVALID')
        self.times, self.values = [], []
        for row in samples:
            require(isinstance(row, dict) and finite(row.get('stageM')), 'STAGE_SAMPLE_INVALID')
            offset = (utc(row.get('timeUtc')) - self.start).total_seconds()
            require(float(offset * 1000).is_integer(), 'STAGE_TIME_PRECISION_INVALID')
            if self.times:
                require(offset > self.times[-1], 'STAGE_TIME_ORDER_INVALID')
                require(offset - self.times[-1] <= maximum_gap, 'STAGE_OBSERVATION_GAP')
            self.times.append(offset)
            self.values.append(float(row['stageM']))
        require(self.times[0] <= 0 and self.times[-1] >= self.duration, 'STAGE_COVERAGE_INCOMPLETE')
        self.knots = tuple(t for t in self.times if 0 < t < self.duration)
        self.summary = {'referenceStatus': reference, 'verticalDatum': specification['verticalDatum'],
            'startUtc': self.start.isoformat(), 'durationSeconds': self.duration,
            'sampleCount': len(samples), 'maximumGapSeconds': maximum_gap,
            'interpolation': 'LINEAR', 'extrapolation': 'FORBIDDEN',
            'endpointClockRoundoffUlp': 8,
            'momentum': momentum_policy, 'evidence': specification['evidence'],
            'rankingEligible': False}
        if reference == 'VERIFIED_ABSOLUTE':
            self.summary['datumEvidence'] = specification['datumEvidence']

    def __call__(self, seconds):
        seconds = clamp_clock_roundoff(seconds, self.times[0], self.times[-1],
                                       'STAGE_TIME_OUTSIDE_OBSERVATIONS')
        index = bisect_right(self.times, seconds) - 1
        value = self.values[index]
        if index < len(self.times) - 1:
            fraction = (seconds - self.times[index]) / (self.times[index + 1] - self.times[index])
            value += fraction * (self.values[index + 1] - value)
        return [value, 0., 0.]


def compile_stage_boundaries(model):
    conditions = model.get('boundaryConditions', {})
    require(isinstance(conditions, dict) and all(isinstance(spec, dict) for spec in conditions.values()),
            'STAGE_SPECIFICATION_INVALID')
    return {name: StageSeries(spec, model) for name, spec in conditions.items()
            if spec.get('type') == 'TIME_SERIES_STAGE'}


def require_network_start(network, start):
    options, section = {}, ''
    for line in network['inputText'].splitlines():
        fields = line.split(';', 1)[0].split()
        if fields and fields[0].startswith('['):
            section = fields[0].upper()
        elif len(fields) == 2 and section == '[OPTIONS]':
            options[fields[0].upper()] = fields[1]
    try:
        network_start = datetime.strptime(options['START_DATE'] + ' ' + options['START_TIME'],
                                           '%m/%d/%Y %H:%M:%S').replace(tzinfo=timezone.utc)
    except (KeyError, ValueError):
        raise FloodModelError('STAGE_NETWORK_CLOCK_INVALID') from None
    require(network.get('timeZone') == 'UTC' and network_start == start,
            'STAGE_NETWORK_CLOCK_MISMATCH')


def require_stage_clock(surface, *, duration, rainfall=None, network=None):
    series = compile_stage_boundaries(surface)
    if not series:
        return series
    require(surface['durationSeconds'] == duration, 'STAGE_WINDOW_MISMATCH')
    start = utc(surface['startUtc'])
    if rainfall is not None:
        require(start == utc(rainfall.get('startUtc')) and
                (utc(rainfall.get('endUtc')) - start).total_seconds() == duration,
                'STAGE_RAIN_CLOCK_MISMATCH')
    if network is not None:
        require_network_start(network, start)
    return series


def source_hash():
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
