"""외부 월류 시간 관측기의 출처·전체 계산 기간 검증."""
import ctypes as C
import math

from . import network
from .flood_errors import require

METHOD = 'NATIVE_EXTERNAL_FLOODING_END_STEP_SECONDS_V1'


def identity(build):
    require(build.get('nodeFloodDurationVersion') == 1, 'NODE_FLOOD_DURATION_VERSION_INVALID')
    for key, source in (
        ('nodeFloodDurationSha256', 'simulation/native/node_flood_duration.inc'),
        ('nodeFloodDurationBuilderSha256', 'scripts/attach_node_flood_duration.py'),
    ):
        require(build.get(key) == network.sha256(network.ROOT/source),
                'NODE_FLOOD_DURATION_IDENTITY_INVALID')
    return {'nodeFloodDurationAdapterSha256': network.sha256(__file__)}


class NodeFloodDurationMixin:
    def snapshot(self):
        value = super().snapshot()
        require(self.lib.wl_floodDurationVersion() == 1, 'NODE_FLOOD_DURATION_VERSION_INVALID')
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
