"""연결 시설의 선행 관측 연속 실행과 같은 시각의 평가 수지 분리."""
import json
import math
from pathlib import Path

from waterleague_sim.engine.connected_facilities import compile_design
from waterleague_sim.engine.flood_errors import FloodModelError, require
from waterleague_sim.engine.flood_process import EngineProcess
from waterleague_sim.engine.network import _TOTAL_FIELDS, sha256
from waterleague_sim.engine.network_quality import routing_balance
from waterleague_sim.engine.initialized_metrics import validate_evaluation_metrics
from waterleague_sim.forcing.network_initialization import prepare_initialized_network

_CUMULATIVE = ('inflowM3', 'evaporationM3', 'infiltrationM3', 'surfaceOutflowM3', 'drainOutflowM3')


def _write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + '\n')


def evaluation_ledger(origin, final, metrics=None):
    start, end = origin['totals']['timeSeconds'], final['totals']['timeSeconds']
    require(0 < start < end, 'FACILITY_INITIALIZATION_EVALUATION_INVALID')
    for state, expected in ((origin, start), (final, end)):
        require(all(math.isclose(row['hydrologyTimeSeconds'], expected, rel_tol=0, abs_tol=1e-7)
                    for row in state['facilities']), 'FACILITY_INITIALIZATION_HYDROLOGY_CLOCK_MISMATCH')
    initial = {(row['subcatchmentId'], row['swmmId']): row for row in origin['facilities']}
    finished = {(row['subcatchmentId'], row['swmmId']): row for row in final['facilities']}
    require(initial and initial.keys() == finished.keys()
            and len(initial) == len(origin['facilities']) == len(final['facilities']),
            'FACILITY_INITIALIZATION_IDENTITIES_MISMATCH')
    facilities = []
    for key, row in finished.items():
        before = initial[key]
        require(row['areaM2'] == before['areaM2'] and row['number'] == before['number'],
                'FACILITY_INITIALIZATION_CONFIGURATION_CHANGED')
        values = {k: row[k]-before[k] for k in _CUMULATIVE}
        incoming = values['inflowM3'] + before['finalStorageM3']
        outgoing = math.fsum(values[k] for k in _CUMULATIVE[1:]) + row['finalStorageM3']
        residual, tolerance = incoming-outgoing, max(1e-8, .01*max(incoming, outgoing))
        require(all(math.isfinite(v) and v >= -1e-10 for v in values.values()),
                'FACILITY_INITIALIZATION_COUNTER_REVERSED')
        facilities.append({'subcatchmentId': key[0], 'swmmId': key[1], **values,
            'initialStorageM3': before['finalStorageM3'], 'finalStorageM3': row['finalStorageM3'],
            'balanceResidualM3': residual, 'allowedResidualM3': tolerance,
            'numericalStatus': 'PASSED' if abs(residual) <= tolerance else 'FAILED'})
    totals = {k: final['totals'][k]-origin['totals'][k] for k in _TOTAL_FIELDS[3:]}
    totals.update(initialStorageM3=origin['totals']['storageM3'], storageM3=final['totals']['storageM3'])
    routing = routing_balance(totals)
    passed = (all(row['numericalStatus'] == 'PASSED' for row in facilities)
              and abs(routing['residualM3']) <= routing['allowedResidualM3'])
    result = {'durationSeconds': end-start, 'facilities': facilities,
        'routingTotals': totals, 'routingBalance': routing, 'numericalStatus': 'PASSED' if passed else 'FAILED',
        'scope': 'SEPARATE_FACILITY_AND_ROUTING_CONTROL_VOLUMES', 'scoreExcludesWarmup': True,
        'peakFlowM3s': None, 'peakStatus': 'NOT_DERIVED_FROM_SPARSE_FRAMES'}
    if metrics is not None:
        validate_evaluation_metrics(origin, final, metrics)
        result.update(peakFlowM3s=metrics['combined']['peakOutwardM3s'],
            peakTimeSeconds=metrics['combined']['peakOutwardTimeSeconds'],
            peakStatus='NATIVE_ALL_EXTERNAL_OUTFALLS_EVALUATION_WINDOW',
            outfallMetrics=metrics)
    return result


def run_initialized_facilities(model, specification, initialization, design, directory):
    prepared = prepare_initialized_network(model, specification, initialization)
    raw, metadata = compile_design(prepared.model['inputText'].encode(), design)
    seconds = prepared.summary['warmupSeconds'] + prepared.summary['evaluationSeconds']
    warmup = prepared.summary['warmupSeconds']
    directory = Path(directory).resolve()
    require(not directory.exists(), 'FACILITY_INITIALIZATION_OUTPUT_EXISTS')
    directory.mkdir(parents=True)
    _write(directory/'request.json', {'network': model, 'observation': specification,
                                      'initialization': initialization, 'design': design})
    prepared.archive(directory/'observations')
    _write(directory/'design.json', metadata)
    (directory/'network-original.inp').write_text(model['inputText'])
    (directory/'observed-network.inp').write_text(prepared.model['inputText'])
    origin, state = None, None
    try:
        window = {'schemaVersion': 1, 'startMilliseconds': warmup*1000, 'endMilliseconds': seconds*1000}
        with EngineProcess('facility_metrics', prepared.model | {'inputText': raw.decode(), 'evaluationWindow': window},
                           directory/'network', evaluation_seconds=seconds) as process:
            state = process.info['initial']
            _write(directory/'seed-state.json', state)
            with (directory/'network-frames.jsonl').open('x') as frames:
                clock = 0
                while clock < seconds:
                    # 같은 고정 경계로 재생하며 평가 경계의 상태를 재설정하지 않는다.
                    step = min(3600, seconds-clock, warmup-clock if clock < warmup else seconds-clock)
                    state = process.call('advance', step)
                    clock += step
                    require(math.isclose(state['totals']['timeSeconds'], clock, rel_tol=0, abs_tol=1e-7),
                            'FACILITY_INITIALIZATION_ROUTING_CLOCK_MISMATCH')
                    frames.write(json.dumps(state, allow_nan=False) + '\n')
                    if clock == warmup:
                        origin = state
                        _write(directory/'evaluation-initial-state.json', origin)
                result = process.call('finish')
        ledger = evaluation_ledger(origin, result['final'], result['evaluationMetrics'])
        passed = result['numericalStatus'] == ledger['numericalStatus'] == 'PASSED'
        report = {'schemaVersion': 2, 'method': prepared.summary['method'], 'rankingEligible': False,
            'classification': 'OBSERVED_FORCING_REFERENCE_FACILITY_DESIGN_NOT_FIELD_VALIDATION',
            'numericalStatus': 'PASSED' if passed else 'FAILED', 'initialization': prepared.summary,
            'design': metadata, 'evaluationLedger': ledger, 'engine': result['engine'],
            'wholeRunNumericalStatus': result['numericalStatus'], 'wholeRunFacilityQuality': result['facilityQuality'],
            'evaluationInitialFacilities': origin['facilities'], 'evaluationFinalFacilities': result['final']['facilities'],
            'limitations': ['관망 단독 초기화이며 2D 지표 상태의 선행 계산을 포함하지 않음',
                '유출 계산과 라우팅이 일치한 경계의 내부 상태; 현장 수분 관측 아님',
                '문헌 설계·명시한 시작 시드 유지; 기간/시드 비교 없이 완전 수렴 주장 불가'],
            'adapterSha256': sha256(__file__),
            'files': {str(p.relative_to(directory)): sha256(p) for p in sorted(directory.rglob('*')) if p.is_file()}}
        _write(directory/'initialized-facilities-result.json', report)
        return report
    except BaseException as error:
        _write(directory/'initialized-facilities-failure.json', {'status': 'FAILED',
            'code': str(error) if isinstance(error, FloodModelError) else 'FACILITY_INITIALIZATION_FAILED',
            'evaluationInitialState': origin, 'lastNetwork': state})
        raise
