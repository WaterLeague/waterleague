"""공식 EPA 격자 유입부의 실제 포착·지표 반환 관측."""
import ctypes as C
import json
import math

from . import network, facility_metrics
from .flood_errors import require
from ..ingestion.published_network import records

FIELDS = ('capturedM3', 'backflowM3', 'netTransferToSewerM3', 'captureActiveSeconds',
    'backflowActiveSeconds', 'peakCapturedM3s', 'peakBackflowM3s', 'peakApproachM3s',
    'observedSeconds', 'routingSteps')


def library_path():
    return network.ROOT/'tmp/inlet-network-swmm-build/install/bin'/network.library_path().name


def identity():
    path = library_path()
    require(path.is_file(), 'INLET_ENGINE_REQUIRED')
    build = json.loads((path.parent/'network-build.json').read_text())
    require(build.get('engineVersion') == '5.2.4' and build.get('revision') == network.REVISION
        and build.get('binarySha256') == network.sha256(path)
        and build.get('facilityObserverVersion') == build.get('metricsVersion') == build.get('inletObserverVersion') == 1,
        'INLET_ENGINE_IDENTITY_INVALID')
    require(build.get('nodeFloodingMethod') == 'EPA_EXTERNAL_FLOODING_EXCLUDING_CAPTURE_RETURNS',
            'INLET_FLOOD_LEDGER_METHOD_INVALID')
    for key, source in (('observerSha256', 'simulation/native/network_snapshot.inc'),
        ('facilityObserverSha256', 'simulation/native/connected_lid_snapshot.inc'),
        ('metricsSha256', 'simulation/native/network_metrics.inc'),
        ('inletObserverSha256', 'simulation/native/inlet_snapshot.inc'),
        ('builderSha256', 'scripts/build_inlet_network_swmm.py')):
        require(build.get(key) == network.sha256(network.ROOT/source), 'INLET_ENGINE_IDENTITY_INVALID')
    return build | {'adapterSha256': network.sha256(__file__),
        'facilityMetricsAdapterSha256': network.sha256(facility_metrics.__file__),
        'facilityAdapterSha256': network.sha256(network.ROOT/'simulation/waterleague_sim/engine/facility_network.py'),
        'metricsAdapterSha256': network.sha256(network.ROOT/'simulation/waterleague_sim/engine/network_metrics.py'),
        'baseAdapterSha256': network.sha256(network.__file__),
        'qualityAdapterSha256': network.sha256(network.ROOT/'simulation/waterleague_sim/engine/network_quality.py')}


class InletNetworkSession(facility_metrics.FacilityMetricsSession):
    engine_path = staticmethod(library_path)
    engine_identity = staticmethod(identity)

    def __enter__(self):
        super().__enter__()
        try:
            require(self.input_units == 'CMS' and self.lib.wl_inletVersion() == 1, 'INLET_OBSERVER_VERSION_INVALID')
            self.lib.wl_inletRead.argtypes = [C.c_int, C.POINTER(C.c_double), C.c_int, C.POINTER(C.c_int)]
            self.lib.wl_inletRelease.restype = None
            self.inlet_rows = [row['tokens'] for row in records(self.input_text.encode())[1].get('INLET_USAGE', [])]
            require(self.inlet_rows and len({r[0].upper() for r in self.inlet_rows}) == len(self.inlet_rows),
                    'INLET_OBSERVER_USAGE_INVALID')
            self._check(self.lib.wl_inletBegin())
            self.inlet_state()
            return self
        except BaseException:
            self.close()
            raise

    def inlet_state(self):
        rows = []
        names = {index: name for name, index in self.nodes.items()}
        for tokens in self.inlet_rows:
            raw = (C.c_double*len(FIELDS))()
            nodes = (C.c_int*2)()
            self._check(self.lib.wl_inletRead(self.links[tokens[0]], raw, len(raw), nodes))
            require(all(math.isfinite(v) for v in raw) and names[nodes[1]] == tokens[2],
                    'INLET_OBSERVER_NATIVE_MISMATCH')
            row = dict(zip(FIELDS, raw)) | {'conduitId': tokens[0], 'designId': tokens[1],
                'bypassNodeId': names[nodes[0]], 'captureNodeId': names[nodes[1]]}
            require(math.isclose(row['capturedM3']-row['backflowM3'], row['netTransferToSewerM3'],
                    rel_tol=1e-10, abs_tol=1e-9), 'INLET_INTERNAL_LEDGER_MISMATCH')
            rows.append(row)
        return {'method': 'EPA_NATIVE_INLET_ROUTING_STEP_V1', 'inlets': rows,
            'integration': 'APPLIED_NATIVE_CAPTURE_AND_RETURN_RATES_TIMES_ROUTING_STEP',
            'classification': 'INTERNAL_TRANSFER_NOT_EXTERNAL_DISCHARGE', 'rankingEligible': False,
            'backflowMethod': 'EPA_CAPTURE_NODE_OVERFLOW_DISTRIBUTION_NOT_2D_HEAD_COUPLING',
            'nodeFloodingMethod': 'EPA_EXTERNAL_FLOODING_EXCLUDING_CAPTURE_RETURNS'}

    def finish(self):
        inlets = self.inlet_state()
        result = super().finish()
        result['inletOperation'] = inlets
        for row in inlets['inlets']:
            require(math.isclose(row['observedSeconds'], result['final']['totals']['timeSeconds'],
                rel_tol=0, abs_tol=1e-6), 'INLET_OBSERVER_TIME_MISMATCH')
        (self.directory/'network-result.json').write_text(json.dumps(result, allow_nan=False, indent=2)+'\n')
        return result

    def close(self):
        if self.opened: self.lib.wl_inletRelease()
        super().close()
