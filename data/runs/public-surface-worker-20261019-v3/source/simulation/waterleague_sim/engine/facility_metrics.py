"""관망 계산을 변경하지 않는 모든 외부 출구의 내부 단계 첨두 관측."""
import ctypes as C
from copy import deepcopy
import json

from . import facility_network, network, network_metrics
from .flood_errors import require


def evaluation_specification(model, seconds, outfalls):
    specification = {'schemaVersion': 1, 'policyVersion': 'PUBLIC_NETWORK_ALL_OUTFALLS_v1',
        'startMilliseconds': 0, 'endMilliseconds': round(seconds * 1000),
        'networkOutfalls': sorted(outfalls)}
    if model is None or 'evaluationWindow' not in model:
        return specification
    window = model['evaluationWindow']
    require(isinstance(window, dict) and set(window) == {
        'schemaVersion', 'startMilliseconds', 'endMilliseconds'}
        and type(window['schemaVersion']) is int and window['schemaVersion'] == 1,
        'FACILITY_METRICS_WINDOW_INVALID')
    start, end = window['startMilliseconds'], window['endMilliseconds']
    require(type(start) is int and type(end) is int and 0 <= start < end <= round(seconds * 1000),
        'FACILITY_METRICS_WINDOW_INVALID')
    return specification | deepcopy(window) | {'policyVersion': 'PUBLIC_NETWORK_ALL_OUTFALLS_WINDOW_v1'}


def library_path():
    return network.ROOT / 'tmp/facility-metrics-swmm-build/install/bin' / network.library_path().name


def identity():
    path = library_path()
    require(path.is_file(), 'FACILITY_METRICS_ENGINE_REQUIRED')
    build = json.loads((path.parent / 'network-build.json').read_text())
    require(build.get('engineVersion') == '5.2.4' and build.get('revision') == network.REVISION
            and build.get('binarySha256') == network.sha256(path)
            and build.get('facilityObserverVersion') == build.get('metricsVersion') == 1,
            'FACILITY_METRICS_ENGINE_IDENTITY_INVALID')
    for key, relative in (
        ('observerSha256', 'simulation/native/network_snapshot.inc'),
        ('facilityObserverSha256', 'simulation/native/connected_lid_snapshot.inc'),
        ('metricsSha256', 'simulation/native/network_metrics.inc'),
        ('builderSha256', 'scripts/build_facility_metrics_swmm.py'),
    ):
        require(build.get(key) == network.sha256(network.ROOT / relative),
                'FACILITY_METRICS_ENGINE_IDENTITY_INVALID')
    return build | {'adapterSha256': network.sha256(__file__),
        'facilityAdapterSha256': network.sha256(facility_network.__file__),
        'metricsAdapterSha256': network.sha256(network_metrics.__file__),
        'baseAdapterSha256': network.sha256(network.__file__),
        'qualityAdapterSha256': network.sha256(network.ROOT / 'simulation/waterleague_sim/engine/network_quality.py')}


class FacilityMetricsSession(facility_network.FacilityNetworkSession):
    engine_path = staticmethod(library_path)
    engine_identity = staticmethod(identity)
    metric_state = network_metrics.MetricsNetworkSession.metric_state

    def __enter__(self):
        super().__enter__()
        try:
            require(self.lib.wl_metricsVersion() == 1, 'NETWORK_METRICS_VERSION_MISMATCH')
            self.lib.wl_metricsBegin.argtypes = [C.c_double, C.c_double, C.POINTER(C.c_int), C.c_int]
            self.lib.wl_metricsRead.argtypes = [C.c_int, C.POINTER(C.c_double), C.c_int]
            self.lib.wl_metricsRelease.restype = None
            # 선택 설계에 따라 유리한 출구를 고르지 않고 원 관망의 모든 외부 출구를 고정한다.
            self.metric_outfalls = sorted(k for k, v in self.initial['nodes'].items() if v['type'] == 1)
            require(self.metric_outfalls, 'NETWORK_METRICS_EXTERNAL_OUTFALL_REQUIRED')
            self.metric_spec = evaluation_specification(
                self.original_model, self.evaluation_seconds, self.metric_outfalls)
            start = self.metric_spec['startMilliseconds'] / 1000
            end = self.metric_spec['endMilliseconds'] / 1000
            nodes = (C.c_int * len(self.metric_outfalls))(*(self.nodes[n] for n in self.metric_outfalls))
            self._check(self.lib.wl_metricsBegin(start, end, nodes, len(nodes)))
            if self.original_model is not None and 'evaluationWindow' in self.original_model:
                (self.directory / 'evaluation-window.json').write_text(
                    json.dumps(self.metric_spec, allow_nan=False, indent=2) + '\n')
            return self
        except BaseException:
            self.close()
            raise

    def finish(self):
        metrics = self.metric_state() | {'specification': self.metric_spec}
        result = super().finish()
        result['evaluationMetrics'] = metrics
        if not metrics['complete']:
            result['numericalStatus'] = 'FAILED'
        (self.directory / 'network-result.json').write_text(json.dumps(result, allow_nan=False, indent=2) + '\n')
        return result

    def close(self):
        if self.opened:
            self.lib.wl_metricsRelease()
        super().close()
