"""동일 평가 창의 원 지표·절대 개선량·보조 비율과 미산정 사유."""
from datetime import datetime
from fractions import Fraction
import math

from .exception import require
from ..engine.node_flood_duration import WINDOW_METHOD

METHOD = 'SIGNED_ABSOLUTE_PRIMARY_RELATIVE_AUXILIARY_V1'
DEFINITIONS = {
    'surfaceDischargeM3': ('m3', 'SELECTED_SURFACE_OUTLET', 'DECREASE'),
    'surfaceAccountedVolumeM3': ('m3', 'SELECTED_SURFACE_OUTLET_WITH_NET_STORAGE', 'DECREASE'),
    'surfacePeakM3s': ('m3/s', 'SELECTED_SURFACE_OUTLET', 'DECREASE'),
    'networkOutflowM3': ('m3', 'ALL_NETWORK_EXTERNAL_OUTFALLS', 'DECREASE'),
    'networkPeakM3s': ('m3/s', 'ALL_NETWORK_EXTERNAL_OUTFALLS', 'DECREASE'),
    'networkFloodingM3': ('m3', 'NETWORK_EXTERNAL_NODE_FLOODING', 'DECREASE'),
    'networkFloodingSeconds': ('s', 'NETWORK_EXTERNAL_NODE_FLOODING', 'DECREASE'),
    'surfaceDepthAreaTimeM3Hours': ('m3*h', 'CONNECTED_SURFACE_GRID', 'DECREASE'),
    'reusedVolumeM3': ('m3', 'VERIFIED_USE_DEMAND', 'INCREASE'),
}


def finite(value):
    try:
        valid = type(value) in (int, float) and math.isfinite(value)
    except (OverflowError, TypeError, ValueError):
        valid = False
    require(valid, 'RAW_METRIC_NUMBER_INVALID')
    return value


def change(key, baseline=None, strategy=None, *, reason=None, unavailable=False):
    unit, boundary, direction = DEFINITIONS[key]
    for value in (baseline, strategy):
        if value is not None:
            finite(value)
    require(not unavailable or (baseline is None and strategy is None and reason is not None),
            'RAW_METRIC_AVAILABILITY_INVALID')
    if baseline is None or strategy is None:
        reason = reason or 'METRIC_MISSING'
    difference, relative, relative_status = None, None, 'NOT_COMPARABLE'
    if reason is None:
        difference = finite((baseline-strategy) * (1 if direction == 'DECREASE' else -1))
        if baseline <= 0:
            relative_status = 'ZERO_BASELINE' if baseline == 0 else 'NEGATIVE_BASELINE'
        else:
            # 비율은 보조값이다. 작은 기준값·악화·100% 초과를 임의로 절단하지 않는다.
            try:
                relative = float(Fraction(str(difference)) * 100 / Fraction(str(baseline)))
            except OverflowError:
                relative = None
            if relative is None or not math.isfinite(relative) or (relative == 0 and difference != 0):
                relative, relative_status = None, 'NUMERIC_RANGE_EXCEEDED'
            else:
                relative_status = 'COMPUTED'
    return {'id': key, 'unit': unit, 'boundary': boundary, 'preferredDirection': direction,
            'status': 'UNAVAILABLE' if unavailable else 'WITHHELD' if reason else 'COMPARABLE',
            'reason': reason, 'baseline': baseline, 'strategy': strategy,
            'signedImprovement': difference, 'relativeImprovementPercent': relative,
            'relativeStatus': relative_status}


def summary(scope, window, rows, primary):
    require(len(rows) == len(DEFINITIONS) and {r['id'] for r in rows} == set(DEFINITIONS),
            'RAW_METRIC_SET_INVALID')
    return {'schemaVersion': 1, 'method': METHOD, 'scope': scope, 'window': window,
            'primaryMetricId': primary, 'compositeScore': None,
            'relativeUsedForRanking': False, 'metrics': rows}


def surface(comparison):
    before, after = (next(c for c in comparison['cases'] if c['id'] == key)
                     for key in ('baseline', 'strategy'))
    start, end = before['metrics']['start'], before['metrics']['end']
    require(start == after['metrics']['start'] and end == after['metrics']['end']
            and datetime.fromisoformat(start).utcoffset() is not None
            and datetime.fromisoformat(end) > datetime.fromisoformat(start),
            'RAW_METRIC_WINDOW_MISMATCH')
    available = {'surfaceDischargeM3': (before['dischargeM3'], after['dischargeM3']),
                 'surfaceAccountedVolumeM3': (before['accountedDischargeM3'], after['accountedDischargeM3']),
                 'surfacePeakM3s': (before['metrics']['peakM3s'], after['metrics']['peakM3s'])}
    rows = []
    for key in DEFINITIONS:
        if key in available:
            rows.append(change(key, *available[key]))
        else:
            reason = 'NO_USE_DEMAND' if key == 'reusedVolumeM3' else 'NO_SURFACE_GRID' if key == 'surfaceDepthAreaTimeM3Hours' else 'NO_CONVEYANCE_NETWORK'
            rows.append(change(key, reason=reason, unavailable=True))
    return summary('SELECTED_INDEPENDENT_SURFACE', {'kind': 'UTC', 'start': start, 'end': end},
                   rows, 'surfaceAccountedVolumeM3')


def network_duration(case):
    metrics = case.get('evaluationMetrics', {})
    value = metrics.get('floodingDuration')
    if value is None:
        return None
    spec = metrics['specification']
    numbers = [finite(value.get(k)) for k in
               ('floodingSeconds', 'coveredSeconds', 'nativeSteps', 'startSeconds', 'endSeconds')]
    seconds, covered, steps, start, end = numbers
    require(type(value.get('schemaVersion')) is int and value.get('schemaVersion') == 1
            and value.get('method') == WINDOW_METHOD
            and type(value.get('complete')) is bool and start < end
            and start == spec['startMilliseconds']/1000 and end == spec['endMilliseconds']/1000
            and 0 <= seconds <= covered <= end-start+1e-7
            and steps >= 0 and steps % 1 == 0 and (steps > 0) == (covered > 0)
            and covered == metrics['combined']['coveredSeconds']
            and steps == metrics['combined']['nativeSteps']
            and value['complete'] == metrics['complete'] == math.isclose(covered, end-start, rel_tol=0, abs_tol=1e-7),
            'RAW_METRIC_FLOOD_DURATION_INVALID')
    return seconds


def network(result):
    before, after = (next(c for c in result['cases'] if c['id'] == key)
                     for key in ('baseline', 'strategy'))
    a, b = before.get('evaluationMetrics'), after.get('evaluationMetrics')
    same = (a is not None and b is not None and a['specificationSha256'] == b['specificationSha256']
            and a['specification'] == b['specification'])
    reason = 'NUMERICAL_FAILURE' if result['numericalStatus'] != 'PASSED' else 'BOUNDARY_MISMATCH' if not same else None
    if reason is None and any(n.get('facilityType') == 'RAINWATER_CISTERN' and n.get('kind') == 'LID_FACILITY'
                              for n in result.get('flowGraph', {}).get('nodes', [])):
        reason = 'UNMODELED_COVER_RAIN'
    if reason is None and not all(c.get('complete') and c['evaluationMetrics']['complete'] for c in (before, after)):
        reason = 'INCOMPLETE_RUN'
    spec = a['specification'] if same else None
    window = {'kind': 'ELAPSED_SECONDS', 'start': spec['startMilliseconds']/1000,
              'end': spec['endMilliseconds']/1000, 'specificationSha256': a['specificationSha256']} if spec else None
    values = {
        'networkOutflowM3': tuple(c.get('totals', {}).get('outflowM3') for c in (before, after)),
        'networkFloodingM3': tuple(c.get('totals', {}).get('floodingM3') for c in (before, after)),
        'networkPeakM3s': tuple(c.get('evaluationMetrics', {}).get('combined', {}).get('peakOutwardM3s') for c in (before, after)),
    }
    durations = tuple(network_duration(c) for c in (before, after))
    if any(v is not None for v in durations):
        values['networkFloodingSeconds'] = durations
    rows = []
    for key in DEFINITIONS:
        if key in values:
            rows.append(change(key, *values[key], reason=reason))
        else:
            missing = 'NO_USE_DEMAND' if key == 'reusedVolumeM3' else 'NO_SURFACE_GRID' if key == 'surfaceDepthAreaTimeM3Hours' else 'NOT_COLLECTED' if key == 'networkFloodingSeconds' else 'DIFFERENT_EVALUATION_BOUNDARY'
            rows.append(change(key, reason=missing, unavailable=True))
    return summary('PUBLISHED_NETWORK_REFERENCE_DESIGN', window, rows, None)
