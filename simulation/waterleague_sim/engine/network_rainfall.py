"""원 엔진의 누적 집수 강우 투입량을 읽는 별도 세션."""
import ctypes as C
import json
import math

from waterleague_sim.engine import network, network_exchange, network_metrics
from waterleague_sim.engine.flood_errors import require


def library_path():
    return network.ROOT / 'tmp/network-rainfall-swmm-build/install/bin' / network.library_path().name


def identity():
    path = library_path()
    require(path.is_file(), 'NETWORK_RAINFALL_ENGINE_REQUIRED')
    build = json.loads((path.parent / 'network-build.json').read_text())
    require(build.get('engineVersion') == '5.2.4' and build.get('revision') == network.REVISION
            and build.get('binarySha256') == network.sha256(path)
            and build.get('rainfallVersion') == build.get('exchangeVersion') == build.get('metricsVersion') == 1,
            'NETWORK_RAINFALL_IDENTITY_MISMATCH')
    for key, relative in (
        ('observerSha256', 'simulation/native/network_snapshot.inc'),
        ('exchangeSha256', 'simulation/native/network_exchange.inc'),
        ('metricsSha256', 'simulation/native/network_metrics.inc'),
        ('rainfallSha256', 'simulation/native/network_rainfall.inc'),
        ('builderSha256', 'scripts/build_rainfall_swmm.py'),
    ):
        require(build.get(key) == network.sha256(network.ROOT / relative),
                'NETWORK_RAINFALL_IDENTITY_MISMATCH')
    return build | {'adapterSha256':network.sha256(__file__),
        'metricsAdapterSha256':network.sha256(network_metrics.__file__),
        'exchangeAdapterSha256':network.sha256(network_exchange.__file__),
        'baseAdapterSha256':network.sha256(network.__file__),
        'qualityAdapterSha256':network.sha256(network.ROOT / 'simulation/waterleague_sim/engine/network_quality.py')}


class RainfallObserver:
    engine_path = staticmethod(library_path)
    engine_identity = staticmethod(identity)

    def snapshot(self):
        state = super().snapshot()
        require(self.lib.wl_rainfallVersion() == 1, 'NETWORK_RAINFALL_VERSION_MISMATCH')
        self.lib.wl_rainfallSnapshot.argtypes = [C.POINTER(C.c_double), C.c_int]
        raw = (C.c_double * 5)()
        self._check(self.lib.wl_rainfallSnapshot(raw, len(raw)))
        require(all(math.isfinite(v) and v >= 0 for v in raw), 'NETWORK_RAINFALL_NONFINITE')
        state['rainfallInput'] = dict(zip(('hydrologyTimeSeconds', 'grossRainfallM3', 'catchmentAreaM2',
            'declaredCatchmentAreaM2', 'nativeHectaresPerFt2'), raw))
        return state


class RainfallNetworkSession(RainfallObserver, network_exchange.ExchangeNetworkSession):
    pass


class RainfallMetricsSession(RainfallObserver, network_metrics.MetricsNetworkSession):
    pass
