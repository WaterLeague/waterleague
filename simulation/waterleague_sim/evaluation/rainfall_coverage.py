"""원 집수 경계에서 강우 소유권·실제 엔진 입력의 독립 재생 대조."""
from .exception import require, EvaluationError
from ..terrain.rainfall_coverage import validate, digest, network_rainfall_difference, METHOD
from ..engine.flood_errors import FloodModelError


def verify(model, surface, result, root, read, file_digest):
    coverage = model.get('networkRainfallCoverage')
    if coverage is None:
        require('rainfallCoverage' not in result and 'rainfallPartition' not in model.get('surface', {}),
                'EVALUATION_RAIN_PARTITION_UNBOUND')
        return
    try:
        validate(model)
    except FloodModelError:
        raise EvaluationError('EVALUATION_RAIN_PARTITION_INVALID') from None
    require(all(name in result['files'] for name in ('rainfall-coverage.json', 'rainfall_coverage.py')),
            'EVALUATION_RAIN_PARTITION_ARTIFACT_MISSING')
    require(read(root/'rainfall-coverage.json') == coverage
            and file_digest(root/'rainfall_coverage.py') == coverage['implementation']['adapterSha256']
            and surface['engine'].get('rainfallPartitionAdapterSha256') == coverage['implementation']['adapterSha256']
            and result.get('rainfallCoverage') == coverage['totals'] | {
                'method': METHOD, 'coverageSha256': digest(coverage)}, 'EVALUATION_RAIN_PARTITION_MISMATCH')
    actual = read(root/'surface/surface-input.json')
    for key in ('verticesM', 'triangles', 'rainfallOwner', 'rainfallPartition'):
        require(actual.get(key) == model['surface'][key], 'EVALUATION_RAIN_PARTITION_NATIVE_MISMATCH')
    if result.get('networkRainfall') is not None:
        require(result['networkRainfall'].get('geometricAreaDifference') ==
                network_rainfall_difference(coverage, result['networkRainfall']),
                'EVALUATION_RAIN_PARTITION_VOLUME_MISMATCH')
