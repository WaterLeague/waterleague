"""서로 다른 OpenMP 런타임을 공유하지 않는 지속형 계산 프로세스."""
import multiprocessing
import os
from pathlib import Path

from waterleague_sim.engine.flood_errors import FloodModelError, require

_METHODS = {
    'network': frozenset(('snapshot', 'advance', 'set_inflow', 'set_outfall_head', 'finish', 'run')),
    'surface': frozenset(('snapshot', 'advance', 'set_rainfall', 'set_station_rainfall', 'finish')),
    'network_exchange': frozenset(('snapshot', 'port_state', 'exchange_step', 'set_inflow', 'finish')),
    'surface_exchange': frozenset(('snapshot', 'port_state', 'apply_exchange', 'advance_exchange',
                                   'set_rainfall', 'set_station_rainfall', 'store_frame', 'finish')),
}
_METHODS['network_metrics'] = _METHODS['network_exchange'] | {'metric_state'}
_METHODS['facility_network'] = _METHODS['network']
_METHODS['coupled_facility_network'] = _METHODS['network_metrics']
for _engine in ('surface', 'surface_exchange'):
    _METHODS[_engine] = _METHODS[_engine] | {'initialization_state'}


def _serve(connection, engine, model, directory, evaluation_seconds, native_duration):
    # 새 인터프리터에서만 엔진을 로드하며 DB·API 비밀 환경을 전달하지 않는다.
    environment = {key: value for key, value in os.environ.items()
                   if key in ('PATH', 'HOME', 'TMPDIR', 'LANG', 'SYSTEMROOT', 'WINDIR')}
    os.environ.clear()
    os.environ.update(environment | {'OMP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1',
                                     'MKL_NUM_THREADS': '1', 'MPLBACKEND': 'Agg'})
    session = None
    try:
        if engine in ('network', 'network_exchange', 'network_metrics', 'facility_network', 'coupled_facility_network'):
            if engine == 'coupled_facility_network':
                from waterleague_sim.engine.coupled_facility_network import CoupledFacilityNetworkSession as NetworkSession
            elif engine == 'facility_network':
                from waterleague_sim.engine.facility_network import FacilityNetworkSession as NetworkSession
            elif engine == 'network_metrics':
                from waterleague_sim.engine.network_metrics import MetricsNetworkSession as NetworkSession
            elif engine == 'network_exchange':
                from waterleague_sim.engine.network_exchange import ExchangeNetworkSession as NetworkSession
            else:
                from waterleague_sim.engine.network import NetworkSession
            kwargs = {'native_duration': True} if native_duration else {}
            session = NetworkSession(model, directory, evaluation_seconds=evaluation_seconds, **kwargs)
            session.__enter__()
            extra = {'durationSeconds': session.duration_seconds, 'evaluationSeconds': session.evaluation_seconds}
        else:
            if engine == 'surface_exchange':
                from waterleague_sim.engine.surface_exchange import ExchangeSurfaceSession as SurfaceSession
            else:
                from waterleague_sim.engine.surface import SurfaceSession
            session = SurfaceSession(model, directory)
            extra = {'gravityMps2': session.gravity_mps2}
        connection.send({'ok': True, 'value': extra | {'engine': session.engine, 'initial': session.initial}})
        while True:
            command = connection.recv()
            if command == {'method': 'close'}:
                break
            require(isinstance(command, dict) and command.get('method') in _METHODS[engine]
                    and isinstance(command.get('args'), tuple), 'FLOOD_PROCESS_COMMAND_INVALID')
            value = getattr(session, command['method'])(*command['args'])
            connection.send({'ok': True, 'value': value})
    except (EOFError, BrokenPipeError):
        pass
    except BaseException as error:
        try:
            connection.send({'ok': False, 'code': str(error) if isinstance(error, FloodModelError)
                             else 'FLOOD_ENGINE_PROCESS_FAILED'})
        except (EOFError, BrokenPipeError, OSError):
            pass
    finally:
        if engine in ('network', 'network_exchange', 'network_metrics', 'facility_network', 'coupled_facility_network') and session is not None:
            session.close()
        connection.close()


class EngineProcess:
    """계산 작업 내부 전용 RPC. 사용자 지정 메서드·코드 실행 인터페이스 없음."""

    def __init__(self, engine, model, directory, *, evaluation_seconds=None, timeout_seconds=60,
                 native_duration=False):
        require(engine in _METHODS, 'FLOOD_ENGINE_KIND_INVALID')
        require(type(native_duration) is bool and (not native_duration or engine in ('network', 'facility_network')),
                'FLOOD_NATIVE_DURATION_DIAGNOSTIC_ONLY')
        self.native_duration = native_duration
        require(type(timeout_seconds) in (int, float) and 0 < timeout_seconds <= 60,
                'FLOOD_PROCESS_TIMEOUT_INVALID')
        self.engine_kind, self.model = engine, model
        self.directory = str(Path(directory).resolve())
        self.evaluation_seconds = evaluation_seconds
        self.timeout = timeout_seconds
        self.process = self.connection = None

    def __enter__(self):
        require(self.process is None, 'FLOOD_PROCESS_ALREADY_STARTED')
        context = multiprocessing.get_context('spawn')
        self.connection, child = context.Pipe()
        self.process = context.Process(target=_serve, args=(child, self.engine_kind, self.model,
                                      self.directory, self.evaluation_seconds, self.native_duration), daemon=True)
        self.process.start()
        child.close()
        try:
            self.info = self._receive()
            return self
        except BaseException:
            self.close()
            raise

    def _receive(self):
        require(self.connection.poll(self.timeout), 'FLOOD_ENGINE_PROCESS_TIMEOUT')
        try:
            response = self.connection.recv()
        except (EOFError, OSError):
            raise FloodModelError('FLOOD_ENGINE_PROCESS_LOST') from None
        require(response.get('ok'), response.get('code', 'FLOOD_ENGINE_PROCESS_FAILED'))
        return response['value']

    def call(self, method, *args):
        require(self.process is not None and self.process.is_alive()
                and method in _METHODS[self.engine_kind], 'FLOOD_PROCESS_NOT_AVAILABLE')
        try:
            self.connection.send({'method': method, 'args': args})
            return self._receive()
        except BaseException:
            self.close()
            raise

    def close(self):
        if self.process is None:
            return
        if self.process.is_alive():
            try:
                self.connection.send({'method': 'close'})
            except (BrokenPipeError, EOFError, OSError):
                pass
            self.process.join(1)
        if self.process.is_alive():
            self.process.terminate()
            self.process.join(1)
        if self.process.is_alive():
            self.process.kill()
            self.process.join(1)
        self.connection.close()
        self.process.close()
        self.process = self.connection = None

    def __exit__(self, *_):
        self.close()
