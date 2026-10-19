"""한 관망 상태의 펌프·LID·지표 교환과 평가 구간 운전 관측."""
import ctypes as C
import json
import math

from . import network, coupled_facility_network, pump_network
from .flood_errors import require


def library_path():
    return network.ROOT/'tmp/coupled-pump-swmm-build/install/bin'/network.library_path().name


def identity():
    path = library_path()
    require(path.is_file(), 'COUPLED_PUMP_ENGINE_REQUIRED')
    build = json.loads((path.parent/'network-build.json').read_text())
    require(build.get('engineVersion') == '5.2.4' and build.get('revision') == network.REVISION
        and build.get('binarySha256') == network.sha256(path)
        and all(build.get(k) == 1 for k in ('exchangeVersion', 'metricsVersion', 'facilityObserverVersion',
            'pumpObserverVersion', 'pumpEvaluationVersion')), 'COUPLED_PUMP_ENGINE_IDENTITY_INVALID')
    for key, source in (
        ('observerSha256', 'simulation/native/network_snapshot.inc'),
        ('facilityObserverSha256', 'simulation/native/connected_lid_snapshot.inc'),
        ('metricsSha256', 'simulation/native/network_metrics.inc'),
        ('exchangeSha256', 'simulation/native/network_exchange.inc'),
        ('pumpObserverSha256', 'simulation/native/pump_snapshot.inc'),
        ('pumpEvaluationSha256', 'simulation/native/pump_evaluation.inc'),
        ('builderSha256', 'scripts/build_coupled_pump_swmm.py')):
        require(build.get(key) == network.sha256(network.ROOT/source), 'COUPLED_PUMP_ENGINE_IDENTITY_INVALID')
    sources = {'adapterSha256': __file__, 'pumpAdapterSha256': pump_network.__file__,
        'coupledFacilityAdapterSha256': coupled_facility_network.__file__}
    for key, module in (('base', 'network'), ('quality', 'network_quality'),
        ('facility', 'facility_network'), ('metrics', 'network_metrics'), ('exchange', 'network_exchange')):
        sources[key+'AdapterSha256'] = network.ROOT/f'simulation/waterleague_sim/engine/{module}.py'
    return build | {key: network.sha256(path) for key, path in sources.items()}


class CoupledPumpNetworkSession(pump_network.PumpObserverMixin, coupled_facility_network.CoupledFacilityNetworkSession):
    engine_path = staticmethod(library_path)
    engine_identity = staticmethod(identity)

    def __enter__(self):
        super().__enter__()
        try:
            require(self.pump_ids and self.lib.wl_pumpEvaluationVersion() == 1,
                    'COUPLED_PUMP_EVALUATION_REQUIRED')
            self.lib.wl_pumpEvaluationBegin.argtypes = [C.c_double, C.c_double]
            self.lib.wl_pumpEvaluationRead.argtypes = [C.c_int, C.POINTER(C.c_double), C.c_int]
            self.lib.wl_pumpEvaluationRelease.restype = None
            self._check(self.lib.wl_pumpEvaluationBegin(self.metric_spec['startMilliseconds']/1000,
                                                       self.metric_spec['endMilliseconds']/1000))
            return self
        except BaseException:
            self.close()
            raise

    def evaluation_pump_state(self):
        result = self._pump_state(self.lib.wl_pumpEvaluationRead)
        start, end = (self.metric_spec[k]/1000 for k in ('startMilliseconds', 'endMilliseconds'))
        return result | {'startSeconds': start, 'endSeconds': end,
            'complete': all(math.isclose(p['observedSeconds'], end-start, abs_tol=1e-7, rel_tol=0)
                            for p in result['pumps']),
            'statePolicy': 'CONTINUOUS_STATE_WARMUP_EXCLUDED_NO_FALSE_START'}

    def finish(self):
        window = self.evaluation_pump_state()
        result = super().finish()
        result['pumpOperation']['evaluation'] = window
        if not window['complete'] or window['curveStatus'] != 'PASSED':
            result['numericalStatus'] = 'FAILED'
        (self.directory/'network-result.json').write_text(json.dumps(result, allow_nan=False, indent=2)+'\n')
        return result

    def close(self):
        if self.opened: self.lib.wl_pumpEvaluationRelease()
        super().close()
