"""수평 유입부의 EPA 수리식과 관망 누적 수지를 지표 결합에 노출."""
import ctypes as C
import json
import math

from waterleague_sim.engine.flood_errors import require
from waterleague_sim.engine import network
from waterleague_sim.engine.network_quality import convergence_state


def library_path():
    return network.ROOT / 'tmp/network-exchange-swmm-build/install/bin' / network.library_path().name


def identity():
    path = library_path()
    require(path.is_file(), 'EXCHANGE_ENGINE_REQUIRED')
    build = json.loads((path.parent / 'network-build.json').read_text())
    require(build.get('engineVersion') == '5.2.4' and build.get('revision') == network.REVISION
            and build.get('binarySha256') == network.sha256(path)
            and build.get('observerSha256') == network.sha256(network.ROOT / 'simulation/native/network_snapshot.inc')
            and build.get('exchangeVersion') == 1
            and build.get('exchangeSha256') == network.sha256(network.ROOT / 'simulation/native/network_exchange.inc'),
            'EXCHANGE_ENGINE_IDENTITY_MISMATCH')
    return build | {'adapterSha256': network.sha256(__file__),
                    'baseAdapterSha256': network.sha256(network.__file__),
                    'qualityAdapterSha256': network.sha256(
                        network.ROOT / 'simulation/waterleague_sim/engine/network_quality.py')}


class ExchangeNetworkSession(network.NetworkSession):
    engine_path = staticmethod(library_path)
    engine_identity = staticmethod(identity)

    def __init__(self, model, directory, *, evaluation_seconds=None):
        self.model = model
        super().__init__(model['inputText'], directory, evaluation_seconds=evaluation_seconds)

    def __enter__(self):
        super().__enter__()
        try:
            require(self.lib.wl_exchangeVersion() == 1, 'EXCHANGE_ENGINE_VERSION_MISMATCH')
            self.lib.wl_exchangeAdvance.argtypes = [C.c_int]
            self.lib.wl_exchangeClockSettings.argtypes = [C.POINTER(C.c_double), C.c_int]
            self.lib.wl_exchangePort.argtypes = [C.c_int, C.c_double, C.POINTER(C.c_double), C.c_int]
            clock = (C.c_double * 3)()
            self._check(self.lib.wl_exchangeClockSettings(clock, 3))
            require(all(math.isfinite(v) and v >= .001
                        and math.isclose(1000 * v, round(1000 * v), abs_tol=1e-8, rel_tol=0)
                        for v in clock[:2]), 'EXCHANGE_MILLISECOND_ROUTING_REQUIRED')
            self.engine['routingClock'] = dict(zip(('maximumSeconds', 'minimumSeconds', 'courantFactor'), clock))
            self.ports = self.model['ports']
            require(isinstance(self.ports, list) and 0 < len(self.ports) <= 10_000,
                    'EXCHANGE_PORTS_REQUIRED')
            for key in ('id', 'outfall', 'orifice'):
                values = [row.get(key) for row in self.ports]
                require(all(isinstance(v, str) and v for v in values)
                        and len(set(values)) == len(values), 'EXCHANGE_PORT_IDENTIFIER_INVALID')
            for row in self.ports:
                require(row['outfall'] in self.nodes and row['orifice'] in self.links
                        and type(row.get('crestM')) in (int, float) and math.isfinite(row['crestM'])
                        and row.get('evidence'), 'EXCHANGE_PORT_REFERENCE_REQUIRED')
            section = ''
            for line in self.input_text.splitlines():
                tokens = line.split(';', 1)[0].upper().split()
                if tokens and tokens[0].startswith('['):
                    section = tokens[0]
                elif section == '[CONTROLS]' and tokens:
                    require(not any(row['orifice'].upper() in tokens for row in self.ports),
                            'EXCHANGE_PORT_CONTROL_REJECTED')
            self.port_state({row['id']: row['crestM'] for row in self.ports})
            return self
        except BaseException:
            self.close()
            raise

    def port_state(self, heads):
        require(self.started and set(heads) == {p['id'] for p in self.ports}, 'EXCHANGE_HEADS_INVALID')
        result = {}
        for row in self.ports:
            head = heads[row['id']]
            require(type(head) in (float, int) and math.isfinite(head), 'EXCHANGE_HEADS_INVALID')
            v = (C.c_double * 11)()
            self._check(self.lib.wl_exchangePort(self.links[row['orifice']], head, v, len(v)))
            require(all(math.isfinite(value) for value in v) and all(v[i] > 0 for i in (3, 4, 5)),
                    'EXCHANGE_PORT_HYDRAULICS_INVALID')
            require(int(v[1]) == self.nodes[row['outfall']]
                    and math.isclose(v[2], row['crestM'], abs_tol=1e-7, rel_tol=0),
                    'EXCHANGE_PORT_DATUM_MISMATCH')
            result[row['id']] = dict(zip(('networkNodeIndex', 'outfallNodeIndex', 'crestM',
                'openingAreaM2', 'dischargeCoefficient', 'transitionDepthM', 'maximumInflowM3s',
                'previousInflowM3s', 'networkToSurfaceM3', 'surfaceToNetworkM3', 'networkHeadM'), v))
        return result

    def exchange_step(self, milliseconds, heads):
        before = self._totals()['timeSeconds']
        require(type(milliseconds) is int and 1 <= milliseconds <= 60_000
                and before + milliseconds / 1000 <= self.evaluation_seconds + 1e-8,
                'EXCHANGE_STEP_INVALID')
        self.port_state(heads)
        for row in self.ports:
            # 같은 단계의 경계 입력은 결합 원장에 한 번 보존한다.
            self.lib.swmm_setValue(304, self.nodes[row['outfall']], heads[row['id']] / self.length_scale)
        self._check(self.lib.wl_exchangeAdvance(milliseconds))
        result = {'totals': self._totals(), 'convergence': convergence_state(self.lib)}
        require(math.isclose(result['totals']['timeSeconds'], before + milliseconds / 1000,
                             abs_tol=1e-8, rel_tol=0), 'EXCHANGE_NETWORK_TIME_MISMATCH')
        return {'network': result, 'ports': self.port_state(heads)}

    def _totals(self):
        raw = (C.c_double * len(network._TOTAL_FIELDS))()
        self._check(self.lib.wl_networkSnapshot(raw, len(raw)))
        result = dict(zip(network._TOTAL_FIELDS, raw))
        require(all(math.isfinite(v) for v in result.values()), 'NETWORK_NONFINITE_RESULT')
        return result
