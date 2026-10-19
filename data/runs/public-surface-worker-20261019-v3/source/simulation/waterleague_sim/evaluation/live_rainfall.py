"""결합 계산의 원 응답→관망 INP→실제 투입량 계보 대조."""
import math
import json

from .exception import require
from waterleague_sim.forcing.live_network_rainfall import compile_network
from waterleague_sim.forcing.live_rainfall import sha


def verify(model, network, result, root, read):
    detail = result.get('networkRainfall')
    specification = model.get('observedRainfall', {})
    bound = specification.get('schemaVersion') == 2 and bool(model.get('networkRainfallTriangles'))
    require((detail is not None) == bound, 'EVALUATION_NETWORK_RAIN_BINDING_MISMATCH')
    if not bound:
        return model
    prepared, expected = compile_network(model['network'], specification)
    summary = read(root/'network-rainfall.json')
    names = ('method', 'startUtc', 'endUtc', 'stationByCatchment', 'catchmentAreasM2',
             'expectedNetworkRainfallM3', 'originalSha256', 'derivedSha256')
    require(all(detail[k] == summary[k] == expected[k] for k in names)
            and all(detail[k] == v for k,v in summary.items())
            and (root/'rainfall-network.inp').read_bytes() == prepared['inputText'].encode()
            and result['files']['rainfall-network.inp'] == expected['derivedSha256'],
            'EVALUATION_NETWORK_RAIN_INPUT_MISMATCH')
    original = root/'network/network-original.inp'
    actual = original if network.get('stageBoundaries') else root/'network/network.inp'
    require(actual.read_bytes() == prepared['inputText'].encode()
            and network['engine'].get('rainfallVersion') == 1,
            'EVALUATION_NETWORK_RAIN_INPUT_MISMATCH')
    observed = read(root/'observed-rainfall/rainfall-summary.json')
    require(observed['specificationSha256'] == sha(json.dumps(
            specification, sort_keys=True, allow_nan=False).encode())
            and all(result['observedRainfall'][k] == v for k,v in observed.items()),
            'EVALUATION_NETWORK_RAIN_SOURCE_MISMATCH')
    native = network['final']['rainfallInput']
    expected_native = expected['expectedNetworkRainfallM3'] * (.09290304 / (.92903e-5*10000))
    require(detail['nativeInput'] == native and native['nativeHectaresPerFt2'] == .92903e-5
            and math.isclose(native['declaredCatchmentAreaM2'],
                math.fsum(expected['catchmentAreasM2'].values()), rel_tol=1e-8, abs_tol=1e-8)
            and math.isclose(native['hydrologyTimeSeconds'], model['durationSeconds'], rel_tol=0, abs_tol=.002)
            and math.isclose(native['grossRainfallM3'], expected_native, rel_tol=1e-8, abs_tol=1e-8)
            and detail['expectedNativeNetworkRainfallM3'] == expected_native
            and detail['nativeVolumeResidualM3'] == native['grossRainfallM3']-expected_native
            and detail['volumeResidualM3'] == native['grossRainfallM3']-expected['expectedNetworkRainfallM3']
            and detail['unitConversionDifferenceM3'] == expected_native-expected['expectedNetworkRainfallM3']
            and detail['expectedCombinedRainfallM3'] == expected['expectedNetworkRainfallM3']+observed['expectedSurfaceRainfallM3']
            and detail['appliedCombinedRainfallM3'] == native['grossRainfallM3']+result['observedRainfall']['appliedSurfaceRainfallM3'],
            'EVALUATION_NETWORK_RAIN_VOLUME_MISMATCH')
    return model | {'network':prepared}
