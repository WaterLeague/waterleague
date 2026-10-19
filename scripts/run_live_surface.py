"""명시된 지표·결합 입력에 필요한 공식 AWS 응답만 직접 조회하여 실행."""
import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'simulation'))
from waterleague_sim.engine.flood_errors import FloodModelError, require
from waterleague_sim.forcing.live_rainfall import capture
from waterleague_sim.forcing.observed_rainfall import utc
from waterleague_sim.forcing.surface_run import run_observed_surface


def execute(request, output, key):
    require(isinstance(request, dict) and set(request) == {'mode', 'model', 'rainfall'},
            'LIVE_SURFACE_REQUEST_INVALID')
    require(request['mode'] in ('surface', 'coupled'), 'LIVE_SURFACE_REQUEST_INVALID')
    rainfall = request['rainfall']
    require(isinstance(rainfall, dict) and set(rainfall) == {
        'startUtc', 'endUtc', 'stationByTriangle', 'assignmentEvidence'}, 'LIVE_SURFACE_REQUEST_INVALID')
    output = Path(output)
    require(not output.exists(), 'OBSERVED_SURFACE_OUTPUT_EXISTS')
    model = deepcopy(request['model'])
    coupled = request['mode'] == 'coupled'
    if coupled:
        require(not any(model.get(k) for k in ('initialization', 'observedRainfall', 'surfaceRainfall',
                'networkRainfallTriangles')), 'LIVE_SURFACE_FORCING_CONFLICT')
    surface = model['surface'] if coupled else model
    start, end = utc(rainfall['startUtc']), utc(rainfall['endUtc'])
    require(surface.get('rainfallStationIds') is None, 'OBSERVED_RAIN_ASSIGNMENT_CONFLICT')
    if coupled:
        from waterleague_sim.forcing.observed_rainfall import require_network_clock
        require_network_clock(model['network'], rainfall)
        require(model['durationSeconds'] == (end-start).total_seconds(), 'LIVE_SURFACE_CLOCK_MISMATCH')
    if 'startUtc' in surface:
        require(utc(surface['startUtc']) == start, 'LIVE_SURFACE_CLOCK_MISMATCH')
    if 'durationSeconds' in surface:
        require(surface['durationSeconds'] == (end-start).total_seconds(), 'LIVE_SURFACE_CLOCK_MISMATCH')
    spec = capture(surface, rainfall['stationByTriangle'], start, end, key, rainfall['assignmentEvidence'])
    if coupled:
        from waterleague_sim.engine.coupled_flood import run_coupled
        return run_coupled(model | {'observedRainfall':spec}, output)
    return run_observed_surface(model, spec, output)


def main():
    from local_config import load
    from waterleague_sim.ingestion.live import LiveSourceError
    from waterleague_sim.ingestion.rainfall import RainfallQualityError
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    load()
    os.umask(0o077)
    try:
        require(args.input.is_file() and not args.input.is_symlink()
                and args.input.stat().st_size <= 32*1024**2, 'LIVE_SURFACE_REQUEST_INVALID')
        request = json.loads(args.input.read_bytes())
        result = execute(request, args.output, os.environ.get('KMA_API_KEY', ''))
        print(json.dumps({'numericalStatus':result['numericalStatus'],
            'rankingEligible':False, 'rainfall':result['observedRainfall']}, ensure_ascii=False))
    except (FloodModelError, LiveSourceError, RainfallQualityError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from None
    except (ValueError, KeyError, TypeError, OSError):
        print('LIVE_SURFACE_RUN_FAILED', file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == '__main__':
    main()
