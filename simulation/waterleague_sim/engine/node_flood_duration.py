"""외부 월류 시간 관측기의 출처·전체 계산 기간 검증."""
import ctypes as C
import math

from . import network
from .flood_errors import require

METHOD = 'NATIVE_EXTERNAL_FLOODING_END_STEP_SECONDS_V1'
WINDOW_METHOD = 'NATIVE_EXTERNAL_FLOODING_ANY_NODE_WINDOW_SECONDS_V1'
WINDOW_FIELDS = ('floodingSeconds', 'coveredSeconds', 'nativeSteps', 'startSeconds', 'endSeconds')


def identity(build):
    require(build.get('nodeFloodDurationVersion') == 2, 'NODE_FLOOD_DURATION_VERSION_INVALID')
    for key, source in (
        ('nodeFloodDurationSha256', 'simulation/native/node_flood_duration.inc'),
        ('nodeFloodDurationBuilderSha256', 'scripts/attach_node_flood_duration.py'),
    ):
        require(build.get(key) == network.sha256(network.ROOT/source),
                'NODE_FLOOD_DURATION_IDENTITY_INVALID')
    return {'nodeFloodDurationAdapterSha256': network.sha256(__file__)}


class NodeFloodDurationMixin:
    def flooding_duration_state(self):
        self.lib.wl_floodDurationWindowRead.argtypes = [C.POINTER(C.c_double), C.c_int]
        raw = (C.c_double*len(WINDOW_FIELDS))()
        self._check(self.lib.wl_floodDurationWindowRead(raw, len(raw)))
        seconds, covered, steps, start, end = raw
        require(all(math.isfinite(v) for v in raw) and 0 <= seconds <= covered
                and start == self.metric_spec['startMilliseconds']/1000
                and end == self.metric_spec['endMilliseconds']/1000
                and covered <= end-start+1e-7 and steps >= 0 and steps.is_integer()
                and (steps > 0) == (covered > 0), 'NETWORK_FLOOD_DURATION_WINDOW_INVALID')
        return dict(zip(WINDOW_FIELDS, raw)) | {
            'schemaVersion': 1, 'method': WINDOW_METHOD,
            'complete': math.isclose(covered, end-start, abs_tol=1e-7, rel_tol=0)}

    def snapshot(self):
        value = super().snapshot()
        require(self.lib.wl_floodDurationVersion() == 2, 'NODE_FLOOD_DURATION_VERSION_INVALID')
        self.lib.wl_floodDurationRead.argtypes = [C.c_int, C.POINTER(C.c_double), C.c_int]
        end = value['totals']['timeSeconds']
        for name, index in self.nodes.items():
            raw = (C.c_double*3)()
            self._check(self.lib.wl_floodDurationRead(index, raw, 3))
            seconds, covered, steps = raw
            require(all(math.isfinite(v) for v in raw) and 0 <= seconds <= covered
                    and math.isclose(covered, end, abs_tol=1e-6, rel_tol=0)
                    and steps >= 0 and steps.is_integer() and (steps > 0) == (end > 0),
                    'NODE_FLOOD_DURATION_WINDOW_INVALID')
            value['nodes'][name]['floodingSeconds'] = seconds
        value['nodeFloodingDurationMethod'] = METHOD
        return value
