"""고정 EPA DYNWAVE의 관망 상태·경계수위·누적 수지 어댑터."""
import ctypes as C
from datetime import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import threading

from waterleague_sim.engine.flood_errors import require
from waterleague_sim.engine.swmm import ROOT, REVISION

FT3_TO_M3 = 0.3048 ** 3
_LOCK = threading.Lock()
_TOTAL_FIELDS = ('timeSeconds', 'initialStorageM3', 'storageM3', 'dryWeatherInflowM3',
                 'runoffInflowM3', 'groundwaterInflowM3', 'rdiiInflowM3',
                 'externalInflowM3', 'outflowM3', 'floodingM3', 'evaporationM3',
                 'seepageM3', 'reactionLossM3')


def library_path():
    return ROOT / 'tmp/network-swmm-build/install/bin' / (
        'libswmm5.dylib' if platform.system() == 'Darwin' else 'libswmm5.so')


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def identity():
    path = library_path()
    require(path.is_file(), 'NETWORK_ENGINE_REQUIRED')
    try:
        build = json.loads((path.parent / 'network-build.json').read_text())
    except (OSError, ValueError):
        require(False, 'NETWORK_ENGINE_IDENTITY_INVALID')
    require(build.get('engineVersion') == '5.2.4' and build.get('revision') == REVISION
            and build.get('binarySha256') == sha256(path)
            and build.get('observerSha256') == sha256(ROOT / 'simulation/native/network_snapshot.inc'),
            'NETWORK_ENGINE_IDENTITY_MISMATCH')
    return build | {'adapterSha256': sha256(__file__), 'platform': platform.platform()}


class NetworkSession:
    """외부 HTTP 입력을 받지 않는 계산 작업용 세션. 프로세스당 관망 하나."""

    def __init__(self, input_text, directory, *, evaluation_seconds=None):
        require(isinstance(input_text, str) and 0 < len(input_text.encode()) <= 2_000_000,
                'NETWORK_INPUT_INVALID')
        # 현재 어댑터는 보존된 단일 INP만 허용하며 외부 파일 참조를 열지 않는다.
        section = ''
        options = {}
        for line in input_text.splitlines():
            row = line.split(';', 1)[0].strip().upper()
            if row.startswith('['):
                section = row
            elif row:
                require(section not in ('[FILES]', '[TEMPERATURE]', '[EVENTS]')
                        and not (section in ('[TIMESERIES]', '[RAINGAGES]', '[EVAPORATION]', '[REPORT]')
                                 and 'FILE' in row.split()),
                        'NETWORK_EXTERNAL_FILE_REJECTED')
                require(section != '[LID_USAGE]' or len(row.split()) < 9 or row.split()[8] == '*',
                        'NETWORK_EXTERNAL_FILE_REJECTED')
                if section == '[OPTIONS]' and len(row.split()) == 2:
                    options[row.split()[0]] = row.split()[1]
        try:
            start = datetime.strptime(options['START_DATE'] + ' ' + options['START_TIME'], '%m/%d/%Y %H:%M:%S')
            end = datetime.strptime(options['END_DATE'] + ' ' + options['END_TIME'], '%m/%d/%Y %H:%M:%S')
        except (KeyError, ValueError):
            require(False, 'NETWORK_EXPLICIT_TIME_REQUIRED')
        self.calendar_seconds = (end - start).total_seconds()
        require(self.calendar_seconds > 0, 'NETWORK_DURATION_INVALID')
        require(evaluation_seconds is None or (type(evaluation_seconds) is int
                and 0 < evaluation_seconds <= self.calendar_seconds), 'NETWORK_EVALUATION_WINDOW_INVALID')
        self.evaluation_seconds = self.calendar_seconds if evaluation_seconds is None else evaluation_seconds
        self.input_text = input_text
        self.directory = Path(directory).resolve()
        self.opened = self.started = self.locked = False
        self.forcing = []
        self.result = None

    def __enter__(self):
        self.engine = identity()
        require(_LOCK.acquire(blocking=False), 'NETWORK_SESSION_ALREADY_OPEN')
        self.locked = True
        try:
            require(not self.directory.exists(), 'NETWORK_OUTPUT_EXISTS')
            require(all(len(os.fsencode(self.directory / name)) <= 259
                        for name in ('network.inp', 'network.rpt', 'network.out')), 'NETWORK_PATH_TOO_LONG')
            self.directory.mkdir(parents=True)
            self.input_path = self.directory / 'network.inp'
            self.input_path.write_text(self.input_text)
            self.lib = C.CDLL(str(library_path()))
            self.lib.swmm_open.argtypes = [C.c_char_p] * 3
            self.lib.swmm_getValue.argtypes = [C.c_int, C.c_int]
            self.lib.swmm_getValue.restype = C.c_double
            self.lib.swmm_setValue.argtypes = [C.c_int, C.c_int, C.c_double]
            self.lib.swmm_setValue.restype = None
            self.lib.swmm_getName.argtypes = [C.c_int, C.c_int, C.c_char_p, C.c_int]
            self.lib.swmm_getName.restype = None
            self.lib.wl_networkAdvance.argtypes = [C.c_int, C.POINTER(C.c_double)]
            self.lib.wl_networkRelease.restype = None
            self.lib.swmm_getMassBalErr.argtypes = [C.POINTER(C.c_float)] * 3
            self.lib.wl_networkSettings.argtypes = [C.POINTER(C.c_double), C.c_int]
            self.lib.wl_networkSnapshot.argtypes = [C.POINTER(C.c_double), C.c_int]
            self.lib.wl_nodeVolumes.argtypes = [C.c_int, C.POINTER(C.c_double), C.c_int]
            require(self.lib.swmm_getVersion() == 52004 and self.lib.wl_networkVersion() == 1,
                    'NETWORK_ENGINE_VERSION_MISMATCH')
            self.opened = True
            self._check(self.lib.swmm_open(*(os.fsencode(self.directory / name)
                        for name in ('network.inp', 'network.rpt', 'network.out'))))
            settings = (C.c_double * 4)()
            self._check(self.lib.wl_networkSettings(settings, 4))
            require(settings[0] == 1 and settings[1] > 0 and settings[2] == 1,
                    'NETWORK_REQUIRES_DYNWAVE_AND_FULL_REPORT_WINDOW')
            self.duration_seconds = settings[1]
            require(self.evaluation_seconds <= self.duration_seconds + .002,
                    'NETWORK_ENGINE_END_TRUNCATED')
            self.ponding_enabled = bool(settings[3])
            units = self.lib.swmm_getValue(8, 0)
            require(units in (0, 3), 'NETWORK_FLOW_UNITS_UNSUPPORTED')
            self.input_units = 'CFS' if units == 0 else 'CMS'
            self.length_scale = .3048 if units == 0 else 1
            # EPA SI 유량/체적 API의 반올림 상수 0.02832를 내부 ft³의 정확한 SI로 변환한다.
            self.flow_scale = FT3_TO_M3 / (1 if units == 0 else .02832)
            self.nodes = self._names(2)
            self.links = self._names(3)
            require(self.nodes and self.links, 'NETWORK_CONVEYANCE_REQUIRED')
            self._check(self.lib.swmm_start(1))
            self.started = True
            self._check(self.lib.wl_networkBegin())
            self.initial = self.snapshot()
            return self
        except BaseException:
            self.close()
            raise

    @staticmethod
    def _check(code):
        require(code == 0, 'NETWORK_ENGINE_ERROR_' + str(code))

    def _names(self, kind):
        result = {}
        for index in range(self.lib.swmm_getCount(kind)):
            name = C.create_string_buffer(256)
            self.lib.swmm_getName(kind, index, name, len(name))
            identifier = name.value.decode('ascii')
            require(identifier and identifier not in result, 'NETWORK_IDENTIFIER_INVALID')
            result[identifier] = index
        return result

    def snapshot(self):
        require(self.started, 'NETWORK_SESSION_NOT_RUNNING')
        raw = (C.c_double * len(_TOTAL_FIELDS))()
        self._check(self.lib.wl_networkSnapshot(raw, len(raw)))
        totals = dict(zip(_TOTAL_FIELDS, raw))
        totals['balanceResidualM3'] = (
            sum(totals[key] for key in _TOTAL_FIELDS[3:8]) + totals['initialStorageM3']
            - sum(totals[key] for key in _TOTAL_FIELDS[8:]) - totals['storageM3'])
        nodes, links = {}, {}
        get = self.lib.swmm_getValue
        for name, index in self.nodes.items():
            volumes = (C.c_double * 6)()
            self._check(self.lib.wl_nodeVolumes(index, volumes, 6))
            nodes[name] = {
                'type': int(get(300, index)), 'headM': get(304, index) * self.length_scale,
                'depthM': get(303, index) * self.length_scale,
                'storageM3': get(305, index) * self.flow_scale,
                'lateralFlowM3s': get(306, index) * self.flow_scale,
                'inflowM3s': get(307, index) * self.flow_scale,
                'overflowM3s': get(308, index) * self.flow_scale,
                'statisticFloodingM3': volumes[0], 'statisticInflowIncludingInitialM3': volumes[1],
                'statisticOutflowM3': volumes[2], 'floodingM3': volumes[3],
                'boundaryOutflowM3': volumes[4], 'boundaryInflowM3': volumes[5],
            }
        for name, index in self.links.items():
            links[name] = {'type': int(get(400, index)), 'flowM3s': get(410, index) * self.flow_scale,
                           'depthM': get(411, index) * self.length_scale, 'setting': get(407, index)}
        require(math.isclose(sum(row['floodingM3'] for row in nodes.values()), totals['floodingM3'],
                             rel_tol=1e-9, abs_tol=1e-8), 'NETWORK_FLOOD_LEDGER_MISMATCH')
        require(all(math.isfinite(value) for row in [totals, *nodes.values(), *links.values()]
                    for value in row.values()), 'NETWORK_NONFINITE_RESULT')
        return {'totals': totals, 'nodes': nodes, 'links': links}

    def advance(self, seconds=None):
        require(self.started, 'NETWORK_SESSION_NOT_RUNNING')
        before = self.snapshot()['totals']['timeSeconds']
        require(before < self.evaluation_seconds, 'NETWORK_ALREADY_AT_END')
        elapsed = C.c_double()
        if seconds is None:
            require(self.evaluation_seconds == self.duration_seconds, 'NETWORK_EXPLICIT_STRIDE_REQUIRED')
            self._check(self.lib.wl_networkAdvance(0, C.byref(elapsed)))
        else:
            require(type(seconds) is int and 1 <= seconds <= 3600, 'NETWORK_STEP_INVALID')
            require(before + seconds <= self.evaluation_seconds + .002, 'NETWORK_STEP_EXCEEDS_EVALUATION')
            self._check(self.lib.wl_networkAdvance(seconds, C.byref(elapsed)))
        result = self.snapshot()
        require(result['totals']['timeSeconds'] > before, 'NETWORK_TIME_NOT_ADVANCING')
        return result

    def set_inflow(self, node, flow_m3s):
        require(self.started and node in self.nodes, 'NETWORK_NODE_INVALID')
        require(type(flow_m3s) in (int, float) and math.isfinite(flow_m3s) and flow_m3s >= 0,
                'NETWORK_INFLOW_INVALID')
        require(self.lib.swmm_getValue(300, self.nodes[node]) != 1, 'NETWORK_OUTFALL_INFLOW_REJECTED')
        self.lib.swmm_setValue(306, self.nodes[node], flow_m3s / self.flow_scale)
        self.forcing.append({'timeSeconds': self.snapshot()['totals']['timeSeconds'],
                             'node': node, 'inflowM3s': flow_m3s})

    def set_outfall_head(self, node, head_m):
        require(self.started and node in self.nodes, 'NETWORK_NODE_INVALID')
        require(type(head_m) in (int, float) and math.isfinite(head_m), 'NETWORK_HEAD_INVALID')
        require(self.lib.swmm_getValue(300, self.nodes[node]) == 1, 'NETWORK_OUTFALL_REQUIRED')
        self.lib.swmm_setValue(304, self.nodes[node], head_m / self.length_scale)
        self.forcing.append({'timeSeconds': self.snapshot()['totals']['timeSeconds'],
                             'node': node, 'outfallHeadM': head_m})

    def run(self, frame_interval_seconds=60):
        require(type(frame_interval_seconds) is int and 1 <= frame_interval_seconds <= 3600,
                'NETWORK_FRAME_INTERVAL_INVALID')
        require(self.evaluation_seconds == self.duration_seconds, 'NETWORK_EXPLICIT_STRIDE_REQUIRED')
        maximum_pump = 0.
        next_frame = 0.
        with (self.directory / 'network-frames.jsonl').open('x') as frames:
            for _ in range(2_000_000):
                row = self.snapshot()
                if row['totals']['timeSeconds'] >= self.duration_seconds:
                    break
                row = self.advance()
                maximum_pump = max(maximum_pump, *(abs(link['flowM3s']) for link in row['links'].values()
                                                   if link['type'] == 1), 0)
                if row['totals']['timeSeconds'] >= next_frame:
                    frames.write(json.dumps(row, allow_nan=False) + '\n')
                    next_frame += frame_interval_seconds
            else:
                require(False, 'NETWORK_STEP_LIMIT_EXCEEDED')
        return {'result': self.finish(), 'maximumPumpFlowM3s': maximum_pump}

    def finish(self):
        require(self.started, 'NETWORK_SESSION_NOT_RUNNING')
        final = self.snapshot()
        self._check(self.lib.swmm_end())
        self.started = False
        self._check(self.lib.swmm_report())
        errors = [C.c_float() for _ in range(3)]
        self._check(self.lib.swmm_getMassBalErr(*(C.byref(value) for value in errors)))
        require(all(math.isfinite(value.value) for value in errors), 'NETWORK_CONTINUITY_INVALID')
        complete = math.isclose(final['totals']['timeSeconds'], self.evaluation_seconds, abs_tol=.002)
        self.result = {'schemaVersion': 1, 'engine': self.engine, 'inputUnits': self.input_units,
                       'internalVolumeConversionM3PerFt3': FT3_TO_M3,
                       'durationSeconds': self.duration_seconds, 'evaluationSeconds': self.evaluation_seconds,
                       'calendarDurationSeconds': self.calendar_seconds, 'complete': complete,
                       'initial': self.initial, 'final': final, 'forcing': self.forcing,
                       'runoffContinuityPercent': errors[0].value,
                       'routingContinuityPercent': errors[1].value,
                       'warningCount': self.lib.swmm_getWarnings(),
                       'numericalStatus': 'PASSED' if complete and abs(errors[1].value) <= 1
                           and (not self.lib.swmm_getCount(1) or abs(errors[0].value) <= 1) else 'FAILED',
                       'files': {p.name: sha256(p) for p in sorted(self.directory.iterdir()) if p.is_file()}}
        (self.directory / 'network-result.json').write_text(json.dumps(self.result, allow_nan=False, indent=2) + '\n')
        return self.result

    def close(self):
        try:
            if self.started:
                self.lib.swmm_end()
                self.started = False
            if self.opened:
                self.lib.wl_networkRelease()
                self.lib.swmm_close()
                self.opened = False
        finally:
            if self.locked:
                self.locked = False
                _LOCK.release()

    def __exit__(self, *_):
        self.close()
