"""완전한 관측 창을 따라 지표 상태를 연속 계산하는 실행 경로."""
import hashlib
import json
import math
from pathlib import Path

from waterleague_sim.engine.flood_errors import FloodModelError, require
from waterleague_sim.engine.flood_process import EngineProcess
from waterleague_sim.forcing.observed_rainfall import compile_rainfall, utc
from waterleague_sim.forcing.stage import require_stage_clock
from waterleague_sim.forcing.surface_evaporation import require_evaporation_clock


def _write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + '\n')


def run_observed_surface(model, specification, directory):
    duration = (utc(specification.get('endUtc')) - utc(specification.get('startUtc'))).total_seconds()
    require(duration.is_integer(), 'OBSERVED_RAIN_WINDOW_INVALID')
    require_stage_clock(model, duration=duration, rainfall=specification)
    require_evaporation_clock(model, duration=duration, rainfall=specification)
    require(model.get('rainfallStationIds') is None, 'OBSERVED_RAIN_ASSIGNMENT_CONFLICT')
    schedule = compile_rainfall(specification, model, int(duration))
    return run_schedule(model, specification, schedule, directory)


def run_schedule(model, specification, schedule, directory, *, evaluation_start=None):
    duration = schedule.summary['durationSeconds']
    require(evaluation_start is None or type(evaluation_start) is int and 0 < evaluation_start < duration,
            'SURFACE_INITIALIZATION_EVALUATION_INVALID')
    directory = Path(directory).resolve()
    require(not directory.exists(), 'OBSERVED_SURFACE_OUTPUT_EXISTS')
    directory.mkdir(parents=True)
    _write(directory / 'observed-surface-input.json', {'surface': model, 'observedRainfall': specification})
    schedule.archive(directory / 'observed-rainfall')
    surface = model | {'rainfallStationIds': specification['stationByTriangle']}
    last, origin = None, None
    maximum_balance_residual = 0.
    try:
        with EngineProcess('surface', surface, directory / 'surface') as session:
            last = session.info['initial']
            for index, event in enumerate(schedule.events):
                require(math.isclose(last['timeSeconds'], event['timeMilliseconds'] / 1000,
                                     abs_tol=1e-8, rel_tol=0), 'OBSERVED_SURFACE_CLOCK_MISMATCH')
                session.call('set_station_rainfall', event['ratesMmHByStation'])
                end = (schedule.events[index + 1]['timeMilliseconds'] / 1000
                       if index + 1 < len(schedule.events) else duration)
                while last['timeSeconds'] < end:
                    stop = min(end, last['timeSeconds'] + 3600)
                    if evaluation_start is not None and last['timeSeconds'] < evaluation_start < stop:
                        stop = evaluation_start
                    last = session.call('advance', stop - last['timeSeconds'])
                    if evaluation_start is not None and last['timeSeconds'] == evaluation_start and origin is None:
                        origin = session.call('initialization_state')
                        _write(directory / 'evaluation-initial-state.json', origin)
                    maximum_balance_residual = max(maximum_balance_residual, abs(last['balanceResidualM3']))
                    scale = max(session.info['initial']['storageM3'] + max(0., last['sourceNetInflowM3'])
                                + max(0., last['boundaryNetInflowM3']), last['storageM3'])
                    require(abs(last['balanceResidualM3']) <= max(1e-8, .01 * scale),
                            'OBSERVED_SURFACE_BALANCE_FAILED')
            result = session.call('finish')
        native_result = result
        expected = schedule.summary['expectedSurfaceRainfallM3']
        actual = last.get('rainfallM3', last['sourceNetInflowM3'])
        require(math.isclose(actual, expected, rel_tol=1e-8, abs_tol=1e-8),
                'OBSERVED_RAIN_VOLUME_MISMATCH')
        result = {'schemaVersion': 1, 'classification': model['evidence'],
                  'numericalStatus': result['numericalStatus'], 'rankingEligible': False,
                  'numericalConfiguration': result['numericalConfiguration'],
                  'numericalQuality': result.get('numericalQuality'),
                  'maximumForcingBoundaryBalanceResidualM3': maximum_balance_residual,
                  'observedRainfall': schedule.summary | {'appliedSurfaceRainfallM3': actual,
                      'volumeResidualM3': actual - expected},
                  'final': last, 'codeSha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  'files': {str(p.relative_to(directory)): hashlib.sha256(p.read_bytes()).hexdigest()
                            for p in sorted(directory.rglob('*')) if p.is_file()}}
        if evaluation_start is not None:
            from waterleague_sim.forcing.surface_initialization import evaluation_ledger
            require(origin is not None, 'SURFACE_INITIALIZATION_STATE_MISSING')
            ledger = evaluation_ledger(origin['surface'], last)
            expected_evaluation = schedule.summary['evaluationRainfall']['expectedSurfaceRainfallM3']
            require(math.isclose(ledger['rainfallM3'], expected_evaluation, rel_tol=1e-8, abs_tol=1e-8),
                    'SURFACE_INITIALIZATION_EVALUATION_RAIN_MISMATCH')
            scale = max(ledger['initialStorageM3'] + max(0., ledger['sourceNetInflowM3'])
                        + max(0., ledger['boundaryNetInflowM3']), ledger['finalStorageM3'])
            require(abs(ledger['balanceResidualM3']) <= max(1e-8, .01*scale),
                    'SURFACE_INITIALIZATION_EVALUATION_BALANCE_FAILED')
            result['initialization'] = {'method': 'CONTINUOUS_STATE_WITHOUT_REINITIALIZATION',
                'warmupSeconds': evaluation_start, 'scoreExcludesWarmup': True, 'evaluationLedger': ledger,
                'initialStateFile': 'evaluation-initial-state.json',
                'initialStateSha256': hashlib.sha256((directory / 'evaluation-initial-state.json').read_bytes()).hexdigest(),
                'evidence': 'MODEL_DERIVED_NOT_MEASURED_SOIL_MOISTURE',
                'limitations': ['선행 이전 시드의 영향·기간 민감도 미확정',
                    '지표 증발 전용·EPA 경험식 회복; 식물/토양/지하수 전체 수지 아님']}
            if 'evaluationMetrics' in native_result:
                result['evaluationMetrics'] = native_result['evaluationMetrics']
        _write(directory / 'observed-surface-result.json', result)
        return result
    except BaseException as error:
        _write(directory / 'observed-surface-failure.json', {'status': 'FAILED', 'lastSurface': last,
            'maximumForcingBoundaryBalanceResidualM3': maximum_balance_residual,
            'code': str(error) if isinstance(error, FloodModelError) else 'OBSERVED_SURFACE_FAILED'})
        raise
