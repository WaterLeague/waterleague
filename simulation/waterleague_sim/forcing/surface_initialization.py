"""관측 선행 상태와 평가를 한 실행에 연결하는 지표 초기화."""
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
import math

from waterleague_sim.engine.flood_errors import require
from waterleague_sim.engine.swmm import ROOT
from waterleague_sim.forcing.antecedent_archive import read_antecedent
from waterleague_sim.forcing.observed_rainfall import RainfallSchedule, compile_rainfall, utc
from waterleague_sim.forcing.stage import require_stage_clock
from waterleague_sim.forcing.surface_evaporation import require_evaporation_clock


def prepare_initialized_surface(model, specification, initialization, *, root=ROOT):
    require(isinstance(initialization, dict) and initialization.get('schemaVersion') == 1
            and initialization.get('method') == 'OBSERVED_ANTECEDENT_CONTINUOUS_V1'
            and type(initialization.get('days')) is int and initialization['days'] in (7, 14, 28)
            and initialization.get('evidence'), 'SURFACE_INITIALIZATION_INVALID')
    evaluation_start, end = utc(specification.get('startUtc')), utc(specification.get('endUtc'))
    duration = (end-evaluation_start).total_seconds()
    require(duration.is_integer(), 'OBSERVED_RAIN_WINDOW_INVALID')
    evaluation = compile_rainfall(specification, model, int(duration), root)
    seconds = initialization['days'] * 86400
    start = evaluation_start-timedelta(seconds=seconds)
    references = initialization.get('stations')
    require(isinstance(references, list) and 0 < len(references) <= 100,
            'SURFACE_INITIALIZATION_SOURCES_REQUIRED')
    depths, antecedents, files = {}, [], dict(evaluation.source_files)
    for reference in references:
        rain, _, sources, summary = read_antecedent(reference, root)
        sid = rain['stationId']
        require(sid not in depths and utc(rain['start']) <= start and utc(rain['end']) == evaluation_start,
                'SURFACE_INITIALIZATION_RAIN_BINDING_INVALID')
        offset = (start-utc(rain['start'])).total_seconds()
        require(offset % 60 == 0, 'SURFACE_INITIALIZATION_RAIN_BINDING_INVALID')
        depths[sid] = rain['depthsMm'][int(offset//60):]
        antecedents.append(summary | {'selectedStartUtc': start.isoformat(),
                                      'selectedEndUtc': evaluation_start.isoformat()})
        files.update(sources)
    areas = {s['stationId']: s['surfaceAreaM2'] for s in evaluation.summary['stations']}
    require(set(depths) == set(areas), 'SURFACE_INITIALIZATION_ASSIGNMENT_INCOMPLETE')
    events, previous = [], None
    for index in range(seconds//60):
        rates = {sid: float(Decimal(str(depths[sid][index]))*60) for sid in sorted(depths)}
        if rates != previous:
            events.append({'timeMilliseconds': index*60_000, 'ratesMmHByStation': rates})
        previous = rates
    events.extend(row | {'timeMilliseconds': row['timeMilliseconds'] + seconds*1000} for row in evaluation.events)
    warmup = [{'stationId': sid, 'depthMm': math.fsum(values), 'surfaceAreaM2': areas[sid],
               'expectedVolumeM3': math.fsum(values)*areas[sid]/1000} for sid, values in sorted(depths.items())]
    expected = math.fsum(s['expectedVolumeM3'] for s in warmup)
    combined_stations = []
    for station in evaluation.summary['stations']:
        sid = station['stationId']
        prior = next(row for row in warmup if row['stationId'] == sid)
        source = next(row for row in antecedents if row['stationId'] == sid)
        combined_stations.append({'stationId': sid, 'surfaceAreaM2': areas[sid],
            'depthMm': prior['depthMm'] + station['depthMm'],
            'expectedVolumeM3': prior['expectedVolumeM3'] + station['expectedVolumeM3'],
            'evaluationSourceSha256': station['sourceSha256'], 'antecedentReference': source['reference']})
    summary = evaluation.summary | {'method': initialization['method'], 'startUtc': start.isoformat(),
        'durationSeconds': seconds+int(duration), 'observedIntervalCount': (seconds+int(duration))//60,
        'rateChangeCount': len(events), 'antecedent': antecedents, 'warmupStations': warmup,
        'stations': combined_stations,
        'warmupExpectedRainfallM3': expected, 'evaluationRainfall': evaluation.summary,
        'expectedSurfaceRainfallM3': expected + evaluation.summary['expectedSurfaceRainfallM3'],
        'sourceFiles': {}}
    from waterleague_sim.forcing.observed_rainfall import digest
    summary['sourceFiles'] = {p: digest(body) for p, body in files.items()}
    value = deepcopy(model)
    if 'startUtc' in value:
        require(utc(value['startUtc']) == evaluation_start and value.get('durationSeconds') == duration,
                'SURFACE_INITIALIZATION_MODEL_CLOCK_MISMATCH')
    value.update(startUtc=start.isoformat(), durationSeconds=seconds+int(duration))
    require(value.get('infiltration') is not None and value.get('rainfallStationIds') is None,
            'SURFACE_INITIALIZATION_INFILTRATION_REQUIRED')
    evaporation = value.get('evaporation')
    require(isinstance(evaporation, dict) and evaporation.get('type') == 'ARCHIVED_FAO56',
            'SURFACE_INITIALIZATION_EVAPORATION_REQUIRED')
    require(initialization.get('weatherReference') in references,
            'SURFACE_INITIALIZATION_WEATHER_BINDING_INVALID')
    evaporation.update(type='ARCHIVED_ANTECEDENT_AND_FAO56',
                       antecedentReference=initialization['weatherReference'])
    if 'evaluationMetrics' in value:
        metrics = value['evaluationMetrics']
        require(metrics.get('startMilliseconds') == 0 and metrics.get('endMilliseconds') == duration*1000,
                'SURFACE_INITIALIZATION_METRICS_WINDOW_INVALID')
        metrics.update(startMilliseconds=seconds*1000, endMilliseconds=int(seconds+duration)*1000)
    combined = deepcopy(specification) | {'startUtc': start.isoformat(), 'initialization': deepcopy(initialization),
                                         'evaluationStartUtc': evaluation_start.isoformat()}
    require_stage_clock(value, duration=seconds+duration, rainfall=combined)
    require_evaporation_clock(value, duration=seconds+duration, rainfall=combined)
    return value, combined, RainfallSchedule(events, summary, files), seconds


def evaluation_ledger(origin, final):
    require(0 <= origin['timeSeconds'] < final['timeSeconds'], 'SURFACE_INITIALIZATION_EVALUATION_INVALID')
    keys = ('boundaryNetInflowM3', 'sourceNetInflowM3', 'rainfallM3', 'infiltrationM3',
            'potentialSurfaceEvaporationM3', 'surfaceEvaporationM3', 'unmetSurfaceEvaporationM3',
            'surfaceEvaporationRoundoffM3')
    result = {k: final[k]-origin[k] for k in keys if k in final and k in origin}
    result.update(durationSeconds=final['timeSeconds']-origin['timeSeconds'],
                  initialStorageM3=origin['storageM3'], finalStorageM3=final['storageM3'],
                  balanceResidualM3=origin['storageM3']+result['boundaryNetInflowM3']
                    +result['sourceNetInflowM3']-final['storageM3'])
    return result


def run_initialized_surface(model, specification, initialization, directory):
    from waterleague_sim.forcing.surface_run import run_schedule
    surface, combined, schedule, seconds = prepare_initialized_surface(model, specification, initialization)
    return run_schedule(surface, combined, schedule, directory, evaluation_start=seconds)
