"""보관 기상 원문을 다시 산정하는 기준 증발산 입력. 네트워크 조회 없음."""
from datetime import datetime, timedelta
import hashlib
import json
import math
from pathlib import Path
import re

from waterleague_sim.engine.flood_errors import FloodModelError, require
from waterleague_sim.engine.swmm import ROOT
from waterleague_sim.ingestion import evaporation as hourly
from waterleague_sim.ingestion import daily_evaporation as daily
from waterleague_sim.ingestion.live import ENDPOINT, LiveSourceError
from waterleague_sim.forcing.stage import utc
from waterleague_sim.forcing.reconstruction import equivalent


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _read(root, relative, expected):
    path = root / relative
    require(isinstance(expected, str) and re.fullmatch('[a-f0-9]{64}', expected)
            and not any(p.is_symlink() for p in (path, *path.parents))
            and path.is_file() and path.stat().st_size <= 32 * 1024**2,
            'REFERENCE_ET_SOURCE_INVALID')
    raw = path.read_bytes()
    require(digest(raw) == expected, 'REFERENCE_ET_SOURCE_HASH_MISMATCH')
    return raw


def _json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'REFERENCE_ET_DUPLICATE_FIELD')
            result[key] = value
        return result
    try:
        return json.loads(raw, object_pairs_hook=pairs)
    except (ValueError, UnicodeError):
        raise FloodModelError('REFERENCE_ET_SOURCE_INVALID') from None


def _rebuild_hourly(data, sources, start, end):
    first = start.astimezone(hourly.KST).replace(minute=0)
    last = (end - timedelta(minutes=1)).astimezone(hourly.KST).replace(minute=0)
    lookback = first - timedelta(hours=36)
    stations, radiation, weather = {}, None, {}
    for raw, meta in sources:
        params, endpoint = meta['parameters'], meta['endpoint']
        if endpoint == hourly.STATION_URL:
            at = datetime.strptime(params['tm'], '%Y%m%d%H%M').replace(tzinfo=hourly.KST)
            require(params.get('inf') == 'AWS' and at in (lookback, last) and at not in stations,
                    'REFERENCE_ET_STATION_PERIOD_INVALID')
            stations[at] = hourly.station(raw)
        elif endpoint == hourly.HOURLY_URL:
            require(radiation is None and params['tm1'] == lookback.strftime('%Y%m%d%H%M')
                    and params['tm2'] == last.strftime('%Y%m%d%H%M'), 'REFERENCE_ET_RADIATION_PERIOD_INVALID')
            radiation = hourly.radiation_rows(raw, lookback, last)
        elif endpoint == ENDPOINT:
            begin = datetime.strptime(params['tm1'], '%Y%m%d%H%M').replace(tzinfo=hourly.KST)
            until = datetime.strptime(params['tm2'], '%Y%m%d%H%M').replace(tzinfo=hourly.KST)
            require(first - hourly.HOUR + hourly.MINUTE <= begin <= until <= last,
                    'REFERENCE_ET_WEATHER_PERIOD_INVALID')
            chunk = hourly.meteorology(raw, begin, until)
            require(not weather.keys() & chunk.keys(), 'REFERENCE_ET_WEATHER_OVERLAP')
            weather.update(chunk)
        else:
            require(False, 'REFERENCE_ET_SOURCE_KIND_INVALID')
    require(set(stations) == {lookback, last} and stations[lookback] == stations[last]
            and radiation is not None, 'REFERENCE_ET_STATION_CHANGED_OR_MISSING')
    return hourly.derive(start, end, stations[lookback], radiation, weather)


def read_reference(reference, root=ROOT):
    root = Path(root).resolve()
    require(isinstance(reference, dict), 'REFERENCE_ET_REFERENCE_INVALID')
    name, expected = reference.get('file'), reference.get('sha256')
    require(isinstance(name, str) and re.fullmatch(r'seoul-\d{8}-fao56-v1\.json', name),
            'REFERENCE_ET_REFERENCE_INVALID')
    relative = 'data/derived/evaporation/' + name
    encoded = _read(root, relative, expected)
    data = _json(encoded)
    try:
        start, end = (utc(data[k]).astimezone(hourly.KST) for k in ('start', 'end'))
        seconds = (end - start).total_seconds()
        require(not any(v.second or v.microsecond for v in (start, end))
                and 0 < seconds <= 86400 and seconds % 60 == 0,
                'REFERENCE_ET_PERIOD_INVALID')
        require(data['method'] in (hourly.METHOD, daily.METHOD)
                and data.get('eventId') == name.removesuffix('-fao56-v1.json')
                and isinstance(data.get('ratesMmDay'), list) and len(data['ratesMmDay']) == seconds / 60
                and all(type(v) in (int, float) and math.isfinite(v) and 0 <= v <= 100
                        for v in data['ratesMmDay']), 'REFERENCE_ET_DERIVED_INVALID')
        requests = data.get('sourceRequests')
        require(isinstance(requests, list) and 3 <= len(requests) <= 10, 'REFERENCE_ET_SOURCES_REQUIRED')
        files, sources, request_keys = {relative: encoded}, [], set()
        for meta in requests:
            path = meta.get('rawFile')
            require(isinstance(path, str) and re.fullmatch(r'data/raw/kma-disaster-pet-[a-f0-9]{24}\.txt', path)
                    and isinstance(meta.get('parameters'), dict) and meta['parameters'].get('stn') == '108'
                    and set(meta['parameters']) <= {'inf', 'stn', 'tm', 'tm1', 'tm2', 'help', 'disp'}
                    and meta.get('endpoint') in (hourly.STATION_URL, hourly.HOURLY_URL, daily.URL, ENDPOINT),
                    'REFERENCE_ET_SOURCE_INVALID')
            key = json.dumps([meta['endpoint'], meta['parameters']], sort_keys=True)
            require(key not in request_keys and path not in files, 'REFERENCE_ET_DUPLICATE_SOURCE')
            request_keys.add(key)
            raw = _read(root, path, meta.get('sha256'))
            files[path] = raw
            sources.append((raw, meta))
        require(data.get('sourceHashes') == [meta['sha256'] for _, meta in sources],
                'REFERENCE_ET_SOURCE_LIST_MISMATCH')
        if data['method'] == hourly.METHOD:
            rebuilt = _rebuild_hourly(data, sources, start, end)
            compared = ('ratesMmDay', 'hours', 'station', 'method', 'timePolicy', 'evidence')
            implementation_files = {'evaporation.py': Path(hourly.__file__),
                                    'evapotranspiration.py': Path(hourly.formula.__file__)}
        else:
            used = set()
            def fetch(endpoint, parameters, _key):
                found = [(i, pair) for i, pair in enumerate(sources)
                         if pair[1]['endpoint'] == endpoint and pair[1]['parameters'] == parameters]
                require(len(found) == 1 and found[0][0] not in used, 'REFERENCE_ET_DAILY_SOURCE_MISMATCH')
                used.add(found[0][0])
                return found[0][1]
            rebuilt, _ = daily.observed_daily(start, end, None, fetch)
            require(len(used) == len(sources), 'REFERENCE_ET_UNUSED_SOURCE')
            compared = ('ratesMmDay', 'days', 'station', 'method', 'timePolicy', 'evidence')
            implementation_files = {'daily_evaporation.py': Path(daily.__file__)}
        require(all(equivalent(data.get(k), rebuilt[k]) for k in compared),
                'REFERENCE_ET_DERIVATION_MISMATCH')
        require(set(data.get('implementationHashes', {})) == set(implementation_files),
                'REFERENCE_ET_IMPLEMENTATION_INVALID')
        for name, current in implementation_files.items():
            expected_code = data['implementationHashes'][name]
            require(isinstance(expected_code, str) and re.fullmatch('[a-f0-9]{64}', expected_code),
                    'REFERENCE_ET_IMPLEMENTATION_INVALID')
            if digest(current.read_bytes()) == expected_code:
                raw = current.read_bytes()
            else:
                raw = _read(root, f'data/derived/evaporation/implementations/{expected_code}.py', expected_code)
            files['original-calculation/' + name] = raw
            files[f'data/derived/evaporation/implementations/{expected_code}.py'] = raw
            files['reconstruction-calculation/' + name] = current.read_bytes()
        comparison = Path(__file__).with_name('reconstruction.py')
        files['reconstruction-calculation/reconstruction.py'] = comparison.read_bytes()
        implementation_files['reconstruction.py'] = comparison
        return data, files, {name: digest(path.read_bytes()) for name, path in implementation_files.items()}
    except FloodModelError:
        raise
    except (KeyError, TypeError, ValueError, UnicodeError, LiveSourceError):
        raise FloodModelError('REFERENCE_ET_REBUILD_FAILED') from None
