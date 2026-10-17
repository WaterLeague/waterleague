"""완전한 관측 창을 따라 지표 상태를 연속 계산하는 실행 경로."""
import hashlib
import json
import math
from pathlib import Path

from waterleague_sim.engine.flood_errors import FloodModelError, require
from waterleague_sim.engine.flood_process import EngineProcess
from waterleague_sim.forcing.observed_rainfall import compile_rainfall, utc


def _write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + '\n')


def run_observed_surface(model, specification, directory):
    duration = (utc(specification.get('endUtc')) - utc(specification.get('startUtc'))).total_seconds()
    require(duration.is_integer(), 'OBSERVED_RAIN_WINDOW_INVALID')
    require(model.get('rainfallStationIds') is None, 'OBSERVED_RAIN_ASSIGNMENT_CONFLICT')
    schedule = compile_rainfall(specification, model, int(duration))
    directory = Path(directory).resolve()
    require(not directory.exists(), 'OBSERVED_SURFACE_OUTPUT_EXISTS')
    directory.mkdir(parents=True)
    _write(directory / 'observed-surface-input.json', {'surface': model, 'observedRainfall': specification})
    schedule.archive(directory / 'observed-rainfall')
    surface = model | {'rainfallStationIds': specification['stationByTriangle']}
    last = None
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
                    last = session.call('advance', min(3600, end - last['timeSeconds']))
                    maximum_balance_residual = max(maximum_balance_residual, abs(last['balanceResidualM3']))
                    scale = max(session.info['initial']['storageM3'] + max(0., last['sourceNetInflowM3'])
                                + max(0., last['boundaryNetInflowM3']), last['storageM3'])
                    require(abs(last['balanceResidualM3']) <= max(1e-8, .01 * scale),
                            'OBSERVED_SURFACE_BALANCE_FAILED')
            result = session.call('finish')
        expected = schedule.summary['expectedSurfaceRainfallM3']
        actual = last['sourceNetInflowM3']
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
        _write(directory / 'observed-surface-result.json', result)
        return result
    except BaseException as error:
        _write(directory / 'observed-surface-failure.json', {'status': 'FAILED', 'lastSurface': last,
            'maximumForcingBoundaryBalanceResidualM3': maximum_balance_residual,
            'code': str(error) if isinstance(error, FloodModelError) else 'OBSERVED_SURFACE_FAILED'})
        raise
