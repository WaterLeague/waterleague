"""보관 선행 강우·기상을 원문으로 재산정. 네트워크 조회 없음."""
from datetime import datetime, timedelta
import gzip
import io
import math
from pathlib import Path
import re

from waterleague_sim.engine.flood_errors import FloodModelError, require
from waterleague_sim.engine.swmm import ROOT
from waterleague_sim.forcing.observed_rainfall import _json, _read, digest, utc
from waterleague_sim.ingestion import antecedent, daily_evaporation, evaporation, live
from waterleague_sim.ingestion.rainfall import RainfallQualityError


def read_antecedent(reference, root=ROOT):
    require(isinstance(reference, dict), 'SURFACE_ANTECEDENT_REFERENCE_INVALID')
    name, expected = reference.get('file'), reference.get('sha256')
    require(isinstance(name, str) and re.fullmatch(r'seoul-\d{8}-\d{1,5}-(7|14|28)d-v1.json.gz', name)
            and isinstance(expected, str) and re.fullmatch('[a-f0-9]{64}', expected),
            'SURFACE_ANTECEDENT_REFERENCE_INVALID')
    root = Path(root).resolve()
    relative = 'data/derived/surface-antecedent/' + name
    encoded = _read(root, relative, expected)
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(encoded)) as stream:
            raw = stream.read(32 * 1024**2 + 1)
        require(len(raw) <= 32 * 1024**2, 'SURFACE_ANTECEDENT_SIZE_INVALID')
        data = _json(raw)
    except (OSError, EOFError):
        raise FloodModelError('SURFACE_ANTECEDENT_ARCHIVE_INVALID') from None
    require(isinstance(data, dict) and isinstance(data.get('rainfall'), dict)
            and isinstance(data.get('evaporation'), dict), 'SURFACE_ANTECEDENT_ARCHIVE_INVALID')
    rain, pet = data['rainfall'], data['evaporation']
    start, end = utc(rain.get('start')), utc(rain.get('end'))
    minutes = int((end - start).total_seconds() / 60)
    require(minutes in (7*1440, 14*1440, 28*1440) and (end-start).total_seconds() == minutes*60
            and rain.get('intervalSeconds') == 60 and start.second == start.microsecond == 0
            and isinstance(rain.get('stationId'), str) and re.fullmatch(r'\d{1,5}', rain['stationId']),
            'SURFACE_ANTECEDENT_WINDOW_INVALID')
    require(name == f"seoul-{end.astimezone(live.KST):%Y%m%d}-{rain['stationId']}-{minutes//1440}d-v1.json.gz",
            'SURFACE_ANTECEDENT_REFERENCE_INVALID')
    for values in (rain.get('depthsMm'), pet.get('ratesMmDay')):
        require(isinstance(values, list) and len(values) == minutes
                and all(type(v) in (int, float) and math.isfinite(v) and 0 <= v <= 100 for v in values),
                'SURFACE_ANTECEDENT_VALUES_INVALID')
    files, requests, rows = {relative: encoded}, {}, {}
    for kind, value in (('rainfall', rain), ('evaporation', pet)):
        sources = value.get('sourceRequests')
        require(isinstance(sources, list) and 0 < len(sources) <= 1000,
                'SURFACE_ANTECEDENT_SOURCES_REQUIRED')
        hashes = set()
        for source in sources:
            require(isinstance(source, dict) and isinstance(source.get('rawFile'), str)
                    and re.fullmatch(r'data/raw/kma-disaster-pet-[a-f0-9]{24}.txt', source['rawFile'])
                    and isinstance(source.get('sha256'), str) and re.fullmatch('[a-f0-9]{64}', source['sha256'])
                    and isinstance(source.get('parameters'), dict)
                    and all(isinstance(k, str) and isinstance(v, str) for k, v in source['parameters'].items()),
                    'SURFACE_ANTECEDENT_SOURCE_INVALID')
            body = _read(root, source['rawFile'], source['sha256'])
            require(source.get('bytes') == len(body), 'SURFACE_ANTECEDENT_SOURCE_INVALID')
            files[source['rawFile']] = body
            hashes.add(source['sha256'])
            if kind == 'rainfall':
                require(source.get('endpoint') == live.ENDPOINT
                        and source['parameters'].get('stn') == rain['stationId'],
                        'SURFACE_ANTECEDENT_RAIN_SOURCE_UNSUPPORTED')
                try:
                    first, last = [datetime.strptime(source['parameters'][k], '%Y%m%d%H%M').replace(tzinfo=live.KST)
                                   for k in ('tm1', 'tm2')]
                    parsed = live.parse(body, rain['stationId'], first, last)
                except (KeyError, ValueError, RainfallQualityError):
                    raise FloodModelError('SURFACE_ANTECEDENT_RAW_INVALID') from None
                for at, row in parsed.items():
                    if start-timedelta(minutes=61) <= at <= end:
                        require(at not in rows or rows[at] == row, 'SURFACE_ANTECEDENT_OVERLAP_CHANGED')
                        rows[at] = row
            else:
                require(source.get('endpoint') in (daily_evaporation.URL, evaporation.STATION_URL),
                        'SURFACE_ANTECEDENT_WEATHER_SOURCE_UNSUPPORTED')
                key = (source['endpoint'], tuple(sorted(source['parameters'].items())))
                require(key not in requests or requests[key][0] == body, 'SURFACE_ANTECEDENT_OVERLAP_CHANGED')
                requests[key] = (body, source)
        require(hashes == set(value.get('sourceHashes', [])), 'SURFACE_ANTECEDENT_SOURCE_BINDING_INVALID')
    warnings, intervals = [], []
    try:
        observed = live.normalized(rows, start, end, rolling_warnings=warnings, interval_averages=intervals)
    except (ValueError, RainfallQualityError):
        raise FloodModelError('SURFACE_ANTECEDENT_RAIN_QUALITY_INVALID') from None
    require([r['depthMm'] for r in observed] == rain.get('depthsMm')
            and [r['method'] for r in observed] == rain.get('depthMethods'),
            'SURFACE_ANTECEDENT_RAIN_DERIVATION_MISMATCH')

    def fetch(endpoint, parameters, _key):
        key = (endpoint, tuple(sorted(parameters.items())))
        require(key in requests, 'SURFACE_ANTECEDENT_WEATHER_SOURCE_MISSING')
        return requests[key]

    try:
        reconstructed, _ = antecedent.weather(start, end, '', fetch)
    except (ValueError, UnicodeError) as error:
        if isinstance(error, FloodModelError):
            raise
        raise FloodModelError('SURFACE_ANTECEDENT_WEATHER_QUALITY_INVALID') from None
    require(reconstructed['ratesMmDay'] == pet.get('ratesMmDay')
            and reconstructed['sourceHashes'] == sorted(set(pet.get('sourceHashes', []))),
            'SURFACE_ANTECEDENT_WEATHER_DERIVATION_MISMATCH')
    modules = [Path(__file__), Path(live.__file__), Path(antecedent.__file__),
               Path(daily_evaporation.__file__), Path(evaporation.__file__)]
    summary = {'method': 'RAW_RECONSTRUCTED_ANTECEDENT_AWS_AND_LAGGED_DAILY_FAO56',
        'startUtc': start.isoformat(), 'endUtc': end.isoformat(), 'minutes': minutes,
        'stationId': rain['stationId'], 'qualityWarnings': warnings, 'aggregatedRainIntervals': intervals,
        'originalQualityWarnings': rain.get('qualityWarnings', []),
        'originalAggregatedRainIntervals': rain.get('aggregatedRainIntervals', []),
        'weatherAssumptions': reconstructed['assumptions'], 'reference': reference,
        'reconstructionCode': {p.name: digest(p.read_bytes()) for p in modules},
        'rankingEligible': False}
    for path in modules:
        files['reconstruction/' + path.name] = path.read_bytes()
    return rain, reconstructed, files, summary
