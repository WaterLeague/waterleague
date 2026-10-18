"""선행 상태를 유지하는 관망의 평가 창·출구 지표 공통 검사."""
import math

from .flood_errors import require
from .flood_metrics import specification_hash


def validate_evaluation_metrics(origin, final, metrics):
    start, end = origin['totals']['timeSeconds'], final['totals']['timeSeconds']
    require(0 <= start < end, 'FACILITY_INITIALIZATION_EVALUATION_INVALID')
    require(isinstance(metrics, dict) and isinstance(metrics.get('specification'), dict),
        'FACILITY_INITIALIZATION_METRICS_INVALID')
    spec = metrics['specification']
    outfalls = sorted(k for k, v in origin['nodes'].items() if v['type'] == 1)
    require(spec == {'schemaVersion': 1, 'policyVersion': 'PUBLIC_NETWORK_ALL_OUTFALLS_WINDOW_v1',
        'startMilliseconds': round(start*1000), 'endMilliseconds': round(end*1000),
        'networkOutfalls': outfalls}
        and metrics.get('specificationSha256') == specification_hash(spec)
        and metrics.get('complete') is True
        and isinstance(metrics.get('outfalls'), dict) and set(metrics['outfalls']) == set(outfalls),
        'FACILITY_INITIALIZATION_METRICS_WINDOW_MISMATCH')
    fields = ('outwardVolumeM3', 'inwardVolumeM3', 'peakOutwardM3s', 'peakInwardM3s',
              'peakOutwardTimeSeconds', 'peakInwardTimeSeconds', 'coveredSeconds', 'nativeSteps')
    for row in [metrics.get('combined'), *metrics['outfalls'].values()]:
        require(isinstance(row, dict) and set(row) == set(fields)
            and all(type(row[k]) in (int, float) and math.isfinite(row[k]) and row[k] >= 0 for k in fields)
            and math.isclose(row['coveredSeconds'], end-start, abs_tol=1e-7, rel_tol=0)
            and start <= row['peakOutwardTimeSeconds'] <= end
            and start <= row['peakInwardTimeSeconds'] <= end,
            'FACILITY_INITIALIZATION_METRICS_INVALID')
    return metrics
