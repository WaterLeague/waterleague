"""설치 이후 관측 입력 전체의 EPA 연속 재생과 분별 물리 상태 추출."""
import ctypes as C
import hashlib
import json
import math
import os
import platform
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .swmm import ROOT, REVISION, SimulationQualityError, make_input

FIELDS = (
    'elapsedSeconds', 'precipitationM3', 'evaporationM3', 'infiltrationM3',
    'surfaceRunoffM3', 'lidDrainageM3', 'initialStorageM3', 'storageM3', 'runoffM3s',
    'surfaceDepthMm', 'pavementDepthMm', 'soilMoisture', 'storageDepthMm',
    'lidInflowM3', 'lidEvaporationM3', 'lidInfiltrationM3', 'lidSurfaceRunoffM3',
    'lidDrainageTotalM3', 'lidInitialStorageM3', 'lidStorageM3',
)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def library_path():
    name = 'libswmm5.dylib' if platform.system() == 'Darwin' else 'libswmm5.so'
    return Path(os.environ.get('LIVE_SWMM_LIBRARY', ROOT/'tmp/live-swmm-build/install/bin'/name))


def engine_identity():
    path = library_path()
    try:
        identity = json.loads((path.parent/'live-build.json').read_text())
        if (identity['revision'] != REVISION or identity['engineVersion'] != '5.2.4'
                or identity['observerSha256'] != digest((ROOT/'simulation/native/lid_snapshot.inc').read_bytes())
                or identity['binarySha256'] != digest(path.read_bytes())):
            raise ValueError()
    except (OSError, KeyError, ValueError):
        raise SimulationQualityError('LIVE_ENGINE_IDENTITY_INVALID') from None
    return identity | {'adapterSha256': digest(Path(__file__).read_bytes())}


def validated_period(model):
    try:
        rain = model['rainfall']
        start, end = [datetime.fromisoformat(rain[k]) for k in ('start', 'end')]
        minutes = (end-start).total_seconds()/60
        values = rain['depthsMm']
        if (start.utcoffset() is None or end.utcoffset() is None or start.second or start.microsecond
                or rain['intervalSeconds'] != 60 or minutes < 1 or minutes != int(minutes)
                or len(values) != int(minutes)
                or any(isinstance(v, bool) or not isinstance(v, (int, float))
                       or not math.isfinite(v) or not 0 <= v <= 100 for v in values)
                or len(model['cells']) != 1):
            raise ValueError()
        return start.astimezone(timezone.utc), int(minutes)
    except (KeyError, TypeError, ValueError):
        raise SimulationQualityError('LIVE_FORCING_INVALID') from None


def input_source(model, placements, evaporation):
    start, count = validated_period(model)
    # UTC 기준으로 시각을 고정해 서버 시간대에 따라 관측 구간이 달라지지 않게 한다.
    # EPA 날짜 차의 floor 연산으로 종료 1초가 잘리는 경우를 피한다. 실행은 관측 끝에서 중단한다.
    normalized = model | {'rainfall': model['rainfall'] | {
        'start': start.isoformat(), 'end': (start+timedelta(minutes=count, seconds=1)).isoformat()}}
    source = make_input(normalized, placements)
    if evaporation is not None:
        values = evaporation['ratesMmDay']
        if (len(values) != count or not evaporation.get('method') or not evaporation.get('sourceHashes')
                or any(isinstance(v, bool) or not isinstance(v, (int, float))
                       or not math.isfinite(v) or not 0 <= v <= 100 for v in values)):
            raise SimulationQualityError('LIVE_EVAPORATION_INVALID')
        before = '[EVAPORATION]\nCONSTANT '+str(model['hydrology']['evaporationMmDay'])
        source = source.replace(before, '[EVAPORATION]\nTIMESERIES PET_DATA')
        rows = []
        # SWMM 증발 시계열은 계단값이다. 각 분 시작에 해당 구간의 파생률을 지정한다.
        for i, value in enumerate(values):
            at = start+timedelta(minutes=i)
            rows.append(f'PET_DATA {at:%m/%d/%Y} {at:%H:%M:%S} {value}')
        source = source.replace('[TIMESERIES]\n', '[TIMESERIES]\n'+'\n'.join(rows)+'\n')
    return source


def replay(model, placements, directory, label, evaporation=None):
    start, count = validated_period(model)
    identity = engine_identity()
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    if not label.isidentifier():
        raise SimulationQualityError('LIVE_OUTPUT_LABEL_INVALID')
    cell = model['cells'][0]
    if (len(placements) > 1 or any(p['cellId'] != cell['id']
            or p['facilityType'] not in cell['allowedTypes']
            or isinstance(p['areaM2'], bool) or not math.isfinite(p['areaM2'])
            or not 0 < p['areaM2'] <= cell['maxAreaM2'] for p in placements)):
        raise SimulationQualityError('LIVE_PLACEMENT_INVALID')
    source = input_source(model, placements, evaporation)
    inp, rpt, out = [directory/f'{label}.{ext}' for ext in ('inp', 'rpt', 'out')]
    inp.write_text(source)
    lib = C.CDLL(str(library_path()))
    lib.wl_hydrologySnapshot.argtypes = [C.POINTER(C.c_double), C.c_int]
    lib.wl_hydrologySnapshot.restype = C.c_int
    if lib.swmm_getVersion() != 52004 or lib.wl_snapshotVersion() != 1:
        raise SimulationQualityError('LIVE_ENGINE_VERSION_MISMATCH')

    def check(code):
        if code:
            raise SimulationQualityError('SWMM_ERROR_'+str(code))

    def snapshot():
        raw = (C.c_double*len(FIELDS))()
        status = lib.wl_hydrologySnapshot(raw, len(FIELDS))
        if status != len(placements) or any(not math.isfinite(v) for v in raw):
            raise SimulationQualityError('LIVE_STATE_INVALID')
        state = {k: (None if i >= 9 and raw[i] == -1 else raw[i]) for i, k in enumerate(FIELDS)}
        if any(v is not None and v < -1e-9 for v in state.values()):
            raise SimulationQualityError('LIVE_STATE_NEGATIVE')
        state['at'] = (start+timedelta(seconds=state['elapsedSeconds'])).isoformat()
        state['accountedDischargeM3'] = (state['surfaceRunoffM3']+state['lidDrainageM3']
                                        +state['storageM3']-state['initialStorageM3'])
        state['balanceResidualM3'] = (state['precipitationM3']-state['evaporationM3']
                                     -state['infiltrationM3']-state['accountedDischargeM3'])
        return state

    samples = []
    try:
        check(lib.swmm_open(os.fsencode(inp), os.fsencode(rpt), os.fsencode(out)))
        check(lib.swmm_start(1))
        initial = snapshot()
        elapsed = C.c_double()
        next_minute = 60
        while True:
            check(lib.swmm_step(C.byref(elapsed)))
            current = snapshot()
            seconds = current['elapsedSeconds']
            if seconds >= next_minute-1e-7:
                if abs(seconds-next_minute) > 1e-7:
                    raise SimulationQualityError('LIVE_REPORT_TIME_MISMATCH')
                samples.append(current)
                next_minute += 60
            if len(samples) == count or elapsed.value == 0:
                break
        check(lib.swmm_end())
        check(lib.swmm_report())
        errors = [C.c_float() for _ in range(3)]
        check(lib.swmm_getMassBalErr(*(C.byref(v) for v in errors)))
        warnings = lib.swmm_getWarnings()
    finally:
        lib.swmm_close()
    if (len(samples) != count or not math.isfinite(errors[0].value)
            or abs(errors[0].value) > 1 or warnings):
        raise SimulationQualityError('LIVE_NUMERICAL_QUALITY_FAILED')
    final = samples[-1]
    if abs(final['balanceResidualM3']) > max(1e-8, .01*(final['precipitationM3']+final['initialStorageM3'])):
        raise SimulationQualityError('LIVE_VOLUME_BALANCE_FAILED')
    return {'initial': initial, 'samples': samples, 'final': final,
            'runoffContinuityPercent': errors[0].value, 'warnings': warnings,
            'engine': identity, 'routingStatus': 'NOT_APPLICABLE_NO_CONVEYANCE_NETWORK'}


def experiment(model, placement, directory, evaporation=None):
    directory = Path(directory)
    baseline = replay(model, [], directory, 'baseline', evaporation)
    strategy = replay(model, [placement], directory, 'strategy', evaporation)
    increments = []
    previous = 0.0
    for a, b in zip(baseline['samples'], strategy['samples'], strict=True):
        cumulative = a['accountedDischargeM3']-b['accountedDischargeM3']
        increments.append({'at': a['at'], 'incrementM3': cumulative-previous,
                           'cumulativeM3': cumulative})
        previous = cumulative
    result = {'schemaVersion': 1, 'validationLevel': 'EXPLORATORY', 'official': False,
              'continuity': 'FULL_HISTORY_REPLAY_NO_LID_STATE_RESET',
              'baseline': baseline, 'strategy': strategy, 'contribution': increments,
              'evaporation': evaporation or {'method': 'ASSUMED_MODEL_CONSTANT',
                                            'rateMmDay': model['hydrology']['evaporationMmDay']},
              'assumptions': model['assumptions'],
              'scoreRule': 'BASELINE_MINUS_STRATEGY_RUNOFF_DRAINAGE_AND_NET_STORAGE_M3'}
    for name, value in [('model', model), ('placement', placement), ('result', result)]:
        (directory/f'{name}.json').write_text(json.dumps(value, ensure_ascii=False, allow_nan=False)+'\n')
    (directory/'continuous.py').write_bytes(Path(__file__).read_bytes())
    (directory/'builder.py').write_bytes((Path(__file__).parent/'swmm.py').read_bytes())
    (directory/'lid_snapshot.inc').write_bytes((ROOT/'simulation/native/lid_snapshot.inc').read_bytes())
    (directory/'manifest.json').write_text(json.dumps({
        p.name: digest(p.read_bytes()) for p in sorted(directory.iterdir())
        if p.is_file() and p.name != 'manifest.json'}, indent=2)+'\n')
    return result
