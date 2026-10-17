"""별도 관측 빌드의 외부 출구 체적·동시 합계 첨두. 기존 엔진 보존."""
import ctypes as C
import json
import math

from waterleague_sim.engine import network, network_exchange
from waterleague_sim.engine.flood_errors import require
from waterleague_sim.engine.flood_metrics import specification_hash


def library_path():
    return network.ROOT / 'tmp/network-metrics-swmm-build/install/bin' / network.library_path().name


def identity():
    path = library_path()
    require(path.is_file(), 'NETWORK_METRICS_ENGINE_REQUIRED')
    build = json.loads((path.parent / 'network-build.json').read_text())
    require(build.get('engineVersion') == '5.2.4' and build.get('revision') == network.REVISION
            and build.get('binarySha256') == network.sha256(path)
            and build.get('exchangeVersion') == build.get('metricsVersion') == 1,
            'NETWORK_METRICS_IDENTITY_MISMATCH')
    for key, relative in (
        ('observerSha256', 'simulation/native/network_snapshot.inc'),
        ('exchangeSha256', 'simulation/native/network_exchange.inc'),
        ('metricsSha256', 'simulation/native/network_metrics.inc'),
        ('builderSha256', 'scripts/build_network_swmm.py'),
    ):
        require(build.get(key) == network.sha256(network.ROOT / relative),
                'NETWORK_METRICS_IDENTITY_MISMATCH')
    return build | {'adapterSha256': network.sha256(__file__),
                    'exchangeAdapterSha256': network.sha256(network_exchange.__file__),
                    'baseAdapterSha256': network.sha256(network.__file__)}


class MetricsNetworkSession(network_exchange.ExchangeNetworkSession):
    engine_path = staticmethod(library_path)
    engine_identity = staticmethod(identity)

    def __enter__(self):
        super().__enter__()
        try:
            require(self.lib.wl_metricsVersion() == 1, 'NETWORK_METRICS_VERSION_MISMATCH')
            self.lib.wl_metricsBegin.argtypes = [C.c_double, C.c_double, C.POINTER(C.c_int), C.c_int]
            self.lib.wl_metricsRead.argtypes = [C.c_int, C.POINTER(C.c_double), C.c_int]
            self.lib.wl_metricsRelease.restype = None
            self.metric_spec = self.model['evaluationMetrics']
            self.metric_outfalls = self.metric_spec['networkOutfalls']
            require(self.metric_outfalls and all(n in self.nodes for n in self.metric_outfalls)
                    and len(set(self.metric_outfalls)) == len(self.metric_outfalls)
                    and not set(self.metric_outfalls).intersection(p['outfall'] for p in self.ports),
                    'NETWORK_METRICS_EXTERNAL_OUTFALL_REQUIRED')
            start = self.metric_spec['startMilliseconds'] / 1000
            end = self.metric_spec['endMilliseconds'] / 1000
            require(0 <= start < end <= self.evaluation_seconds, 'FLOOD_METRICS_WINDOW_INVALID')
            nodes = (C.c_int * len(self.metric_outfalls))(*(self.nodes[n] for n in self.metric_outfalls))
            self._check(self.lib.wl_metricsBegin(start, end, nodes, len(nodes)))
            return self
        except BaseException:
            self.close()
            raise

    def metric_state(self):
        rows = []
        for index in range(len(self.metric_outfalls) + 1):
            raw = (C.c_double * 8)()
            self._check(self.lib.wl_metricsRead(index, raw, len(raw)))
            require(all(math.isfinite(v) and v >= 0 for v in raw), 'NETWORK_METRICS_NONFINITE')
            rows.append(dict(zip(('outwardVolumeM3', 'inwardVolumeM3', 'peakOutwardM3s',
                'peakInwardM3s', 'peakOutwardTimeSeconds', 'peakInwardTimeSeconds',
                'coveredSeconds', 'nativeSteps'), raw)))
        expected = (self.metric_spec['endMilliseconds'] - self.metric_spec['startMilliseconds']) / 1000
        return {'specificationSha256': specification_hash(self.metric_spec),
            'complete': math.isclose(rows[-1]['coveredSeconds'], expected, abs_tol=1e-7, rel_tol=0),
            'method': 'NATIVE_ROUTING_STEP_DIRECTIONAL_TRAPEZOIDAL_INTEGRAL',
            'peakMethod': 'SIMULTANEOUS_SELECTED_OUTFALL_SUM',
            'outfalls': dict(zip(self.metric_outfalls, rows[:-1])), 'combined': rows[-1]}

    def finish(self):
        metrics = self.metric_state()
        result = super().finish()
        result['evaluationMetrics'] = metrics
        (self.directory / 'network-result.json').write_text(json.dumps(result, allow_nan=False, indent=2) + '\n')
        return result

    def close(self):
        if self.opened:
            self.lib.wl_metricsRelease()
        super().close()
