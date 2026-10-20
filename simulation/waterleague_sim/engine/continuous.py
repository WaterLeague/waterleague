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
    return identity | {'adapterSha256': digest(Path(__file__).read_bytes()),
        'geometryAdapterSha256': digest((ROOT/'simulation/waterleague_sim/spatial/geometry.py').read_bytes()),
        'facilityAdapterSha256': digest((Path(__file__).parent/'facilities.py').read_bytes()),
        'referenceConditionsAdapterSha256': digest((ROOT/'simulation/waterleague_sim/spatial/reference_conditions.py').read_bytes()),
        'designFootprintAdapterSha256': digest((ROOT/'simulation/waterleague_sim/spatial/design_footprint.py').read_bytes()),
        'referenceScenarioSha256': digest((ROOT/'backend/src/main/resources/facilities/reference-surfaces-v1.json').read_bytes())}


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
    if placements:
        from ..spatial.suitability import SiteSuitabilityError, require_explorable
        try:
            require_explorable(model['cells'][0])
        except SiteSuitabilityError as error:
            raise SimulationQualityError(str(error)) from None
    if 'geometry' in model['cells'][0]:
        from ..spatial.geometry import SiteGeometryError, cell_geometry, dimensions
        cell = model['cells'][0]
        try:
            if cell.get('geometryCrs') != 'EPSG:5186':
                raise SiteGeometryError('SITE_METRIC_CRS_REQUIRED')
            geometry = cell_geometry(cell)
            if (type(cell['maxAreaM2']) not in (int, float) or not math.isfinite(cell['maxAreaM2'])
                    or not 0 < cell['maxAreaM2'] <= geometry.area):
                raise SiteGeometryError('SITE_POLYGON_LIMIT_INVALID')
            expected = dimensions(geometry)
            physical = cell['physicalInputs']
            if (not isinstance(physical, dict) or physical.get('widthMethod') != expected['widthMethod']
                    or any(not math.isclose(physical[key], expected[key], rel_tol=1e-10, abs_tol=1e-6)
                           for key in ('flowLengthM', 'runoffWidthM'))):
                raise SiteGeometryError('SITE_FLOW_DIMENSIONS_INVALID')
        except (SiteGeometryError, KeyError, TypeError, ValueError):
            raise SimulationQualityError('LIVE_SITE_GEOMETRY_INVALID') from None
    for placement in placements:
        if placement['facilityType'] == 'VEGETATIVE_SWALE':
            from .facilities import swale_design
            area = placement['areaM2']
            if (type(area) not in (int, float) or not math.isfinite(area)
                    or not 0 < area <= swale_design(model['cells'][0])['maxAreaM2']):
                raise SimulationQualityError('LIVE_SWALE_DESIGN_INVALID')
    for placement in placements:
        if placement['facilityType'] == 'INFILTRATION_TRENCH':
            from .facilities import trench_design
            area = placement['areaM2']
            if (type(area) not in (int, float) or not math.isfinite(area)
                    or not 0 < area <= trench_design(model['cells'][0])['maxAreaM2']):
                raise SimulationQualityError('LIVE_TRENCH_DESIGN_INVALID')
    # UTC 기준으로 시각을 고정해 서버 시간대에 따라 관측 구간이 달라지지 않게 한다.
    # EPA 날짜 차의 floor 연산으로 종료 1초가 잘리는 경우를 피한다. 실행은 관측 끝에서 중단한다.
    normalized = model | {'rainfall': model['rainfall'] | {
        'start': start.isoformat(), 'end': (start+timedelta(minutes=count, seconds=1)).isoformat()}}
    # 작은 표면·실제 지형 경사에서 10초 적분의 초기 수지 오차를 줄인다.
    source = make_input(normalized, [], step_seconds=1 if model['cells'][0].get('physicalInputs') or model.get('facilityDesignSet') else 10)
    # 등록 모델의 고정 생성기는 보존하고 확장 시설 배치는 연속 계산 계층에서 구성한다.
    identifiers = {'RAIN_GARDEN': 'RG', 'PERMEABLE_PAVEMENT': 'PP', 'GREEN_ROOF': 'GR',
                   'BIORETENTION': 'BC', 'VEGETATIVE_SWALE': 'VS', 'INFILTRATION_TRENCH': 'IT'}
    by_cell = {p['cellId']: p for p in placements}
    usage = []
    for cell in model['cells']:
        placement = by_cell.get(cell['id'])
        if placement is not None:
            area = float(placement['areaM2'])
            kind = identifiers[placement['facilityType']]
            usage.append(f"{cell['id']} {kind} 1 {area} {math.sqrt(area):.6f} "
                         f"{model['hydrology']['initialSaturationPercent']} 100 0 * OUT 0")
    source = source.replace('[LID_USAGE]\n', '[LID_USAGE]\n' + '\n'.join(usage))
    if model.get('facilityDesignSet') is not None:
        rows = []
        for line in source.splitlines():
            if line.startswith('RAIN_DATA '):
                fields = line.split()
                # EPA gage_setState의 내부 +1초 탐색을 상쇄하여 다음 분 강우의 조기 유입 방지.
                at = datetime.strptime(fields[1]+' '+fields[2], '%m/%d/%Y %H:%M:%S')+timedelta(seconds=1)
                line = f'RAIN_DATA {at:%m/%d/%Y} {at:%H:%M:%S} {fields[3]}'
            rows.append(line)
        source = '\n'.join(rows)+'\n'
    if model.get('sharedSiteSource', {}).get('inflowPolicy') == 'DIRECT_RAINFALL_ONLY':
        # 배수 연결 근거가 없는 표면의 유출을 시설에 임의 배분하지 않는다.
        lines, in_usage = [], False
        for line in source.splitlines():
            if line.startswith('['):
                in_usage = line == '[LID_USAGE]'
            elif in_usage and line.strip():
                fields = line.split()
                if len(fields) != 11:
                    raise SimulationQualityError('LIVE_INFLOW_FORMAT_INVALID')
                fields[6] = '0'
                line = ' '.join(fields)
            lines.append(line)
        source = '\n'.join(lines)+'\n'
    physical = model['cells'][0].get('physicalInputs')
    if physical is not None:
        source = apply_site_inputs(source, model['cells'][0], placements)
    if model.get('facilityDesignSet') is not None:
        from .facilities import apply
        source = apply(source, model)
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



def apply_site_inputs(source, cell, placements):
    physical = cell['physicalInputs']
    if physical.get('referenceScenario') is not None:
        from ..spatial.reference_conditions import validate
        validate(cell)
    required = ('runoffWidthM','flowLengthM','slopePercent')
    if (any(isinstance(physical.get(k),bool) or not isinstance(physical.get(k),(float,int))
            or not math.isfinite(physical[k]) for k in required)
            or physical['runoffWidthM']<=0 or physical['flowLengthM']<=0 or physical['slopePercent']<0):
        raise SimulationQualityError('LIVE_SITE_PHYSICS_INVALID')
    for key in ('nImpervious','conductivityMmH','suctionMm'):
        if key in physical and (not isinstance(physical[key],(float,int)) or not math.isfinite(physical[key]) or physical[key]<=0):
            raise SimulationQualityError('LIVE_SITE_PHYSICS_INVALID')
    for key in ('nPervious', 'depressionMm', 'depressionPerviousMm', 'imperviousPercent', 'initialMoistureDeficit'):
        if key in physical and (type(physical[key]) not in (float, int) or not math.isfinite(physical[key]) or physical[key] < 0
                or key == 'imperviousPercent' and physical[key] > 100
                or key == 'initialMoistureDeficit' and physical[key] > 1):
            raise SimulationQualityError('LIVE_SITE_PHYSICS_INVALID')
    lines=[]; section=''
    for line in source.splitlines():
        if line.startswith('['):section=line
        elif line.strip():
            f=line.split()
            if section=='[SUBCATCHMENTS]':
                f[5]=str(physical['runoffWidthM']);f[6]=str(physical['slopePercent'])
                if 'imperviousPercent' in physical:
                    f[4] = str(physical['imperviousPercent'])
            elif section=='[SUBAREAS]' and 'nImpervious' in physical:
                f[1]=str(physical['nImpervious'])
                for index, key in ((2, 'nPervious'), (3, 'depressionMm'), (4, 'depressionPerviousMm')):
                    if key in physical:
                        f[index] = str(physical[key])
            elif section=='[INFILTRATION]' and 'conductivityMmH' in physical:
                f[1]=str(physical['suctionMm']);f[2]=str(physical['conductivityMmH'])
                if 'initialMoistureDeficit' in physical:
                    f[3] = str(physical['initialMoistureDeficit'])
            elif section=='[LID_USAGE]':
                # 미확정 세부 배치 모양은 후보와 같은 종횡비로 축소한 설계로 계산한다.
                f[4]=str(physical['runoffWidthM']*math.sqrt(float(f[3])/cell['areaM2']))
            elif section=='[LID_CONTROLS]':
                if f[0]=='PP' and f[1]=='SURFACE':f[5]=str(physical['slopePercent'])
                if f[0] in ('PP','RG') and f[1]=='STORAGE' and 'conductivityMmH' in physical:
                    f[4]=str(physical['conductivityMmH'])
            line=' '.join(f)
        lines.append(line)
    return '\n'.join(lines)+'\n'

def replay(model, placements, directory, label, evaporation=None, *, evaluation_start_seconds=None):
    start, count = validated_period(model)
    step = 1 if model['cells'][0].get('physicalInputs') or model.get('facilityDesignSet') else 10
    evaluation_start = model.get('initialization', {}).get('warmupMinutes', 0) * 60
    if evaluation_start_seconds is not None:
        if (type(evaluation_start_seconds) is not int
                or not evaluation_start <= evaluation_start_seconds < count * 60
                or evaluation_start_seconds % step):
            raise SimulationQualityError('HISTORICAL_INSTALLATION_TIME_INVALID')
        evaluation_start = evaluation_start_seconds
    identity = engine_identity()
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    if not label.isidentifier():
        raise SimulationQualityError('LIVE_OUTPUT_LABEL_INVALID')
    cell = model['cells'][0]
    if (not math.isfinite(cell['areaM2']) or not 0 < cell['maxAreaM2'] <= cell['areaM2']
            or len(placements) > 1 or any(p['cellId'] != cell['id']
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
    lib.lid_getDrainFlow.argtypes = [C.c_int, C.c_int]
    lib.lid_getDrainFlow.restype = C.c_double
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
    from .runoff_metrics import RunoffMetrics
    metrics = RunoffMetrics(evaluation_start, count * 60, start, step)
    evaluation_origin = None
    metric_state = (C.c_double * len(FIELDS))()
    try:
        check(lib.swmm_open(os.fsencode(inp), os.fsencode(rpt), os.fsencode(out)))
        check(lib.swmm_start(1))
        initial = snapshot()
        if evaluation_start_seconds == 0:
            evaluation_origin = initial
        elapsed = C.c_double()
        next_minute = 60
        while True:
            check(lib.swmm_step(C.byref(elapsed)))
            if lib.wl_hydrologySnapshot(metric_state, len(FIELDS)) != len(placements):
                raise SimulationQualityError('LIVE_STATE_INVALID')
            # 고정 EPA lid.h의 CURRENT=1. 읽기 전용 getter이며 분별 기록에는 필드를 추가하지 않는다.
            drain = lib.lid_getDrainFlow(0, 1) * 0.028316846592
            metrics.observe(metric_state[0], metric_state[8], drain)
            # 분 경계에서만 상태를 복사하여 1초 적분의 Python 변환 비용을 줄인다.
            seconds = elapsed.value*86400
            if evaluation_start_seconds is not None and abs(seconds-evaluation_start_seconds) < 1e-7:
                evaluation_origin = snapshot()
            if seconds >= next_minute-1e-7 or elapsed.value == 0:
                current = snapshot()
                seconds = current['elapsedSeconds']
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
    result = {'initial': initial, 'samples': samples, 'final': final,
            'runoffMetrics': metrics.finish(),
            'runoffContinuityPercent': errors[0].value, 'warnings': warnings,
            'engine': identity, 'routingStatus': 'NOT_APPLICABLE_NO_CONVEYANCE_NETWORK'}
    if evaluation_start_seconds is not None:
        if evaluation_origin is None:
            raise SimulationQualityError('HISTORICAL_INSTALLATION_STATE_MISSING')
        result['evaluationOrigin'] = evaluation_origin
    return result


def experiment(model, placement, directory, evaporation=None, *, installed_at=None):
    directory = Path(directory)
    offset = None
    if installed_at is not None:
        from .temporal import installation_offset
        offset = installation_offset(model, installed_at)
    baseline = replay(model, [], directory, 'baseline', evaporation, evaluation_start_seconds=offset)
    strategy = replay(model, [placement], directory, 'strategy', evaporation, evaluation_start_seconds=offset)
    initialization = None
    if installed_at is not None:
        from .temporal import activation_window
        baseline, strategy, initialization = activation_window(model, baseline, strategy, offset)
    elif model.get('initialization') is not None:
        from .initialization import evaluation_window
        baseline, strategy, initialization = evaluation_window(model, baseline, strategy)
    increments = []
    previous = 0.0
    for a, b in zip(baseline['samples'], strategy['samples'], strict=True):
        cumulative = a['accountedDischargeM3']-b['accountedDischargeM3']
        increments.append({'at': a['at'], 'incrementM3': cumulative-previous,
                           'cumulativeM3': cumulative})
        previous = cumulative
    result = {'schemaVersion': 1, 'validationLevel': 'EXPLORATORY', 'official': False,
              'inflowPolicy': model.get('sharedSiteSource', {}).get('inflowPolicy', 'LEGACY_ALL_IMPERVIOUS_RUNOFF'),
              'continuity': 'FULL_HISTORY_REPLAY_NO_LID_STATE_RESET',
              'baseline': baseline, 'strategy': strategy, 'contribution': increments,
              'evaporation': evaporation or {'method': 'ASSUMED_MODEL_CONSTANT',
                                            'rateMmDay': model['hydrology']['evaporationMmDay']},
              'assumptions': model['assumptions'],
              'scoreRule': 'BASELINE_MINUS_STRATEGY_RUNOFF_DRAINAGE_AND_NET_STORAGE_M3'}
    if initialization is not None:
        result['initialization'] = initialization
    if installed_at is not None:
        result['temporalPolicy'] = 'INSTALLATION_TIME_EXPERIMENT_V1'
        result['installedAt'] = installed_at
        result['assumptions'] = list(model['assumptions']) + initialization['limitations']
        (directory/'temporal.py').write_bytes(Path(__file__).with_name('temporal.py').read_bytes())
    from .runoff_metrics import comparison
    result['runoffComparison'] = comparison(baseline, strategy)
    (directory/'runoff_metrics.py').write_bytes(Path(__file__).with_name('runoff_metrics.py').read_bytes())
    (directory/'raw_metrics.py').write_bytes((Path(__file__).parents[1]/'evaluation/raw_metrics.py').read_bytes())
    if model.get('facilityDesignSet') is not None:
        from .facilities import evidence, source_path
        result['facilityDesign'] = evidence(placement['facilityType'], model)
        (directory/'facility-designs.json').write_bytes(source_path(model).read_bytes())
        (directory/'facilities.py').write_bytes((Path(__file__).parent/'facilities.py').read_bytes())
    if initialization is not None:
        (directory/'initialization.py').write_bytes((Path(__file__).parent/'initialization.py').read_bytes())
    for name, value in [('model', model), ('placement', placement), ('result', result)]:
        (directory/f'{name}.json').write_text(json.dumps(value, ensure_ascii=False, allow_nan=False)+'\n')
    (directory/'continuous.py').write_bytes(Path(__file__).read_bytes())
    (directory/'site_geometry.py').write_bytes((ROOT/'simulation/waterleague_sim/spatial/geometry.py').read_bytes())
    for filename in ('reference_conditions.py', 'design_footprint.py'):
        (directory/filename).write_bytes((ROOT/'simulation/waterleague_sim/spatial'/filename).read_bytes())
    (directory/'reference-surfaces.json').write_bytes((ROOT/'backend/src/main/resources/facilities/reference-surfaces-v1.json').read_bytes())
    (directory/'builder.py').write_bytes((Path(__file__).parent/'swmm.py').read_bytes())
    (directory/'lid_snapshot.inc').write_bytes((ROOT/'simulation/native/lid_snapshot.inc').read_bytes())
    (directory/'manifest.json').write_text(json.dumps({
        p.name: digest(p.read_bytes()) for p in sorted(directory.iterdir())
        if p.is_file() and p.name != 'manifest.json'}, indent=2)+'\n')
    return result
