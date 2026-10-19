"""집수 분할 이용조의 실제 선행 관측·기준안 비교·평가 상태 보존."""
from copy import deepcopy
import json
import math
from pathlib import Path

from .cistern_network import compile_cistern
from .connected_storage import result_summary
from .flood_errors import FloodModelError, require
from .flood_process import EngineProcess
from .initialized_metrics import validate_evaluation_metrics
from .network import _TOTAL_FIELDS, sha256
from .network_quality import routing_balance
from ..forcing.network_initialization import prepare_initialized_network
from ..ingestion.published_network import digest, records


def _write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + '\n')


def prepare_initialized_cistern(model, specification, initialization, design):
    require(isinstance(model, dict) and isinstance(model.get('inputText'), str),
            'CISTERN_INITIALIZATION_MODEL_INVALID')
    original = model['inputText'].encode()
    # 관측 치환으로 해시를 다시 결속하기 전에 원 설계의 출처와 모든 수리 제약을 확인한다.
    compile_cistern(original, design)
    require(not records(original)[1].get('LID_USAGE'), 'CISTERN_INITIALIZATION_EXISTING_LID_UNSUPPORTED')
    prepared = prepare_initialized_network(model, specification, initialization)
    observed = prepared.model['inputText'].encode()
    raw, metadata = compile_cistern(observed, deepcopy(design) | {'sourceNetworkSha256': digest(observed)})
    metadata['originalSourceNetworkSha256'] = digest(original)
    metadata['originalDesign'] = deepcopy(design)
    metadata['forcingSha256'] = prepared.summary['derivedSha256']
    return prepared, raw, metadata


def routing_ledger(origin, result):
    final = result['final']
    metrics = validate_evaluation_metrics(origin, final, result['evaluationMetrics'])
    totals = {key: final['totals'][key]-origin['totals'][key] for key in _TOTAL_FIELDS[3:]}
    totals.update(initialStorageM3=origin['totals']['storageM3'], storageM3=final['totals']['storageM3'])
    balance = routing_balance(totals)
    return {'startSeconds': origin['totals']['timeSeconds'], 'endSeconds': final['totals']['timeSeconds'],
        'routingTotals': totals, 'routingBalance': balance, 'outfallMetrics': metrics,
        'numericalStatus': 'PASSED' if abs(balance['residualM3']) <= balance['allowedResidualM3'] else 'FAILED',
        'scoreExcludesWarmup': True}


def _run(model, warmup, seconds, directory):
    window = {'schemaVersion': 1, 'startMilliseconds': warmup*1000, 'endMilliseconds': seconds*1000}
    origin, state = None, None
    try:
        with EngineProcess('facility_metrics', model | {'evaluationWindow': window},
                           directory, evaluation_seconds=seconds) as process:
            state = process.info['initial']
            _write(directory/'seed-state.json', state)
            with (directory/'initialization-frames.jsonl').open('x') as frames:
                clock = 0
                while clock < seconds:
                    step = min(3600, seconds-clock, warmup-clock if clock < warmup else seconds-clock)
                    state = process.call('advance', step)
                    clock += step
                    require(math.isclose(state['totals']['timeSeconds'], clock, abs_tol=1e-7, rel_tol=0),
                            'CISTERN_INITIALIZATION_CLOCK_MISMATCH')
                    frames.write(json.dumps(state, allow_nan=False) + '\n')
                    if clock == warmup:
                        origin = state
                        _write(directory/'evaluation-initial-state.json', origin)
                result = process.call('finish')
        require(origin is not None, 'CISTERN_INITIALIZATION_BOUNDARY_MISSING')
        return origin, result, routing_ledger(origin, result)
    except BaseException as error:
        directory.mkdir(parents=True, exist_ok=True)
        _write(directory/'initialization-failure.json', {'status': 'FAILED',
            'code': str(error) if isinstance(error, FloodModelError) else 'CISTERN_INITIALIZATION_FAILED',
            'evaluationInitialState': origin, 'lastNetwork': state})
        raise


def comparison(baseline, strategy, storage, baseline_result, strategy_result):
    require(baseline['startSeconds'] == strategy['startSeconds']
        and baseline['endSeconds'] == strategy['endSeconds']
        and baseline['outfallMetrics']['specification'] == strategy['outfallMetrics']['specification'],
        'CISTERN_INITIALIZATION_COMPARISON_WINDOW_MISMATCH')
    before, after = baseline['routingTotals'], strategy['routingTotals']
    delta = after['runoffInflowM3']-before['runoffInflowM3']
    tolerance = max(1e-8, abs(before['runoffInflowM3'])*1e-9)
    passed = all(value == 'PASSED' for value in (baseline['numericalStatus'], strategy['numericalStatus'],
        storage['numericalStatus'], baseline_result['numericalStatus'], strategy_result['numericalStatus']))
    passed = passed and abs(delta) <= tolerance
    metrics = [row['outfallMetrics']['combined'] for row in (baseline, strategy)]
    changes = {'outwardVolumeReductionM3': metrics[0]['outwardVolumeM3']-metrics[1]['outwardVolumeM3'],
        'inwardVolumeReductionM3': metrics[0]['inwardVolumeM3']-metrics[1]['inwardVolumeM3'],
        'peakOutwardReductionM3s': metrics[0]['peakOutwardM3s']-metrics[1]['peakOutwardM3s'],
        'nodeFloodingReductionM3': before['floodingM3']-after['floodingM3'],
        'netStorageIncreaseM3': (after['storageM3']-after['initialStorageM3'])
            -(before['storageM3']-before['initialStorageM3'])}
    return {'numericalStatus': 'PASSED' if passed else 'FAILED', 'rankingEligible': False,
        'sourceRunoffPreservation': {'differenceM3': delta, 'allowedDifferenceM3': tolerance,
            'status': 'PASSED' if abs(delta) <= tolerance else 'FAILED'},
        'rawChanges': changes, 'effects': changes if passed else None,
        'effectStatus': 'EXPLORATORY_NUMERICAL_COMPARISON' if passed else 'WITHHELD_NUMERICAL_FAILURE',
        'storedWaterIsPermanentReduction': False,
        'storageLedgerAlreadyIncludedInRouting': True}


def run_initialized_cistern(model, specification, initialization, design, directory):
    prepared, raw, metadata = prepare_initialized_cistern(model, specification, initialization, design)
    directory = Path(directory).resolve()
    require(not directory.exists(), 'CISTERN_INITIALIZATION_OUTPUT_EXISTS')
    directory.mkdir(parents=True)
    _write(directory/'request.json', {'network': model, 'observation': specification,
                                    'initialization': initialization, 'design': design})
    prepared.archive(directory/'observations')
    _write(directory/'design.json', metadata)
    (directory/'network-original.inp').write_text(model['inputText'])
    (directory/'observed-network.inp').write_text(prepared.model['inputText'])
    warmup = prepared.summary['warmupSeconds']
    seconds = warmup + prepared.summary['evaluationSeconds']
    baseline_origin, baseline, baseline_ledger = _run(prepared.model, warmup, seconds, directory/'baseline')
    strategy_origin, strategy, strategy_ledger = _run(
        prepared.model | {'inputText': raw.decode()}, warmup, seconds, directory/'strategy')
    storage = result_summary(metadata, strategy['initial'], strategy['final'], strategy_origin)
    compared = comparison(baseline_ledger, strategy_ledger, storage, baseline, strategy)
    report = {'schemaVersion': 1, 'method': 'OBSERVED_ANTECEDENT_HYDRAULIC_CISTERN_COMPARISON_V1',
        'classification': 'OBSERVED_FORCING_EXPLICIT_HYDRAULIC_DESIGN_NOT_FIELD_VALIDATION',
        'numericalStatus': compared['numericalStatus'], 'rankingEligible': False,
        'initialization': prepared.summary, 'design': metadata, 'comparison': compared,
        'baselineEvaluation': baseline_ledger, 'strategyEvaluation': strategy_ledger, 'storage': storage,
        'evaluationInitialStorage': strategy_origin['nodes'][metadata['facilities'][0]['nodeId']],
        'baselineEvaluationInitialState': baseline_origin, 'strategyEvaluationInitialState': strategy_origin,
        'baselineWholeRunStatus': baseline['numericalStatus'], 'strategyWholeRunStatus': strategy['numericalStatus'],
        'engine': strategy['engine'], 'adapterSha256': sha256(__file__),
        'evaluationAdapterSha256': sha256(Path(__file__).with_name('initialized_metrics.py')),
        'limitations': ['선행 시작 수심은 명시적 시드이며 평가 시작 수심은 같은 엔진의 연속 계산값',
            '용량 초과 절점 월류는 지표로 연결되지 않았으므로 실패·효과 보류',
            '시설 수지는 관망 수지에 이미 포함되며 두 체적을 합산하지 않음',
            '기존 연결·경계 입력을 유지하며 실제 서울 부지·홈통·시공비 확인을 대체하지 않음',
            '재이용 수요·수질·사용 펌프 미모형화; 배수를 소비나 영구 저감으로 표시하지 않음'],
        'files': {str(p.relative_to(directory)): sha256(p) for p in sorted(directory.rglob('*')) if p.is_file()}}
    _write(directory/'initialized-cistern-result.json', report)
    return report
