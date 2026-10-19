"""완료된 관측 시간의 증발산을 다음 시간에 적용하는 인과적 입력."""
import hashlib
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import build_opener

from .live import KST, LiveSourceError, NoRedirect, fetch_range, parse
from ..engine import evapotranspiration as formula

HOURLY_URL = 'https://apihub.kma.go.kr/api/typ01/url/kma_sfctm3.php'
STATION_URL = 'https://apihub.kma.go.kr/api/typ01/url/stn_inf.php'
METHOD = 'FAO56_HOURLY_LAGGED_ASOS_AWS_V1'
HOUR = timedelta(hours=1)
MINUTE = timedelta(minutes=1)


def fetch(endpoint, parameters, key):
    if not key or endpoint not in (HOURLY_URL, STATION_URL, 'https://apihub.kma.go.kr/api/typ01/url/kma_sfcdd3.php'):
        raise LiveSourceError('KMA_ACCESS_UNAVAILABLE')
    try:
        with build_opener(NoRedirect()).open(endpoint+'?'+urlencode(parameters | {'authKey': key}), timeout=30) as response:
            raw = response.read(4_000_001)
        if len(raw) > 4_000_000 or key.encode() in raw:
            raise LiveSourceError('KMA_RESPONSE_INVALID')
    except HTTPError as error:
        raise LiveSourceError('KMA_ACCESS_UNAVAILABLE' if error.code in (401, 403) else 'KMA_UNAVAILABLE') from None
    except (OSError, TimeoutError):
        raise LiveSourceError('KMA_UNAVAILABLE') from None
    return raw, {'provider': 'KMA_ASOS_DIRECT', 'endpoint': endpoint, 'parameters': parameters,
                 'fetchedAt': datetime.now(timezone.utc).isoformat(), 'sha256': hashlib.sha256(raw).hexdigest(),
                 'purpose': 'SIMULATION_USED_INPUT_ONLY'}


def lines(raw):
    try:
        text = raw.decode('euc-kr')
        if not text.startswith('#START7777') or not text.strip().endswith('#7777END'):
            raise ValueError()
        return [line.split() for line in text.splitlines() if line.strip() and not line.startswith('#')]
    except (ValueError, UnicodeError):
        raise LiveSourceError('KMA_PET_FORMAT_INVALID') from None


def station(raw):
    rows = lines(raw)
    if len(rows) != 1 or len(rows[0]) < 13 or rows[0][0] != '108' or b'HT_WD' not in raw:
        raise LiveSourceError('KMA_PET_STATION_INVALID')
    try:
        lon, lat, elevation, height = (float(rows[0][i]) for i in (1, 2, 4, 5))
        if (not all(math.isfinite(v) for v in (lon, lat, elevation, height)) or not 124 < lon < 132
                or not 32 < lat < 40 or not -100 <= elevation <= 2000 or not .1 <= height <= 100):
            raise ValueError()
        return {'stationId': '108', 'stationName': '서울', 'longitude': lon, 'latitude': lat,
                'elevationM': elevation, 'windHeightM': height}
    except ValueError:
        raise LiveSourceError('KMA_PET_STATION_INVALID') from None


def radiation_rows(raw, start, end):
    result = {}
    try:
        if b'# 35. SI' not in raw:
            raise ValueError()
        for fields in lines(raw):
            if len(fields) != 46 or fields[1] != '108':
                raise ValueError()
            at = datetime.strptime(fields[0], '%Y%m%d%H%M').replace(tzinfo=KST)
            value = float(fields[34])
            if at in result or at.minute or not start <= at <= end or not math.isfinite(value):
                raise ValueError()
            if value < 0 and value not in (-9, -99, -999):
                raise ValueError()
            if value > 10:
                raise ValueError()
            result[at] = None if value < 0 else value
        return result
    except ValueError:
        raise LiveSourceError('KMA_PET_RADIATION_INVALID') from None


def meteorology(raw, start, end):
    result = parse(raw, '108', start, end)
    # 시간 평균 풍속에는 중첩된 10분 평균 대신 AWS 1분 평균을 사용한다.
    if b'WD1' not in raw or b'WS1' not in raw:
        raise LiveSourceError('KMA_PET_WIND_FORMAT_INVALID')
    for fields in (line.split() for line in raw.decode('utf-8').splitlines() if line.strip() and not line.startswith('#')):
        at = datetime.strptime(fields[0], '%Y%m%d%H%M').replace(tzinfo=KST).astimezone(timezone.utc)
        wind = float(fields[3])
        result[at]['windSpeedMs'] = wind if math.isfinite(wind) and 0 <= wind <= 150 else None
    return result


def derive(start, end, metadata, radiation, weather):
    first = start.astimezone(KST).replace(minute=0, second=0, microsecond=0)
    last = (end-MINUTE).astimezone(KST).replace(minute=0, second=0, microsecond=0)
    cloud = None
    hours = {}
    for at in sorted(radiation):
        solar = formula.solar_hour(at, metadata['latitude'], metadata['longitude'], metadata['elevationM'])
        value = radiation[at]
        clear = solar['clearSkyMjM2']
        ratio = None if value is None or clear == 0 else min(1, max(.3, value/clear))
        if solar['beforeSunsetReference'] and ratio is not None:
            cloud = (at, ratio)
        if at < first or at > last:
            continue
        if clear == 0:
            if value not in (None, 0):
                raise LiveSourceError('KMA_PET_NIGHT_RADIATION_INVALID')
            # 일몰 이후 단파복사 0은 태양 위치에 따른 값이며 관측 결측의 일반 대체가 아니다.
            value = 0
            if cloud is None or not timedelta(0) < at-cloud[0] <= timedelta(hours=24):
                raise LiveSourceError('KMA_PET_NIGHT_CLOUD_MISSING')
            ratio = cloud[1]
        if value is None or ratio is None:
            raise LiveSourceError('KMA_PET_RADIATION_MISSING')
        samples = [weather.get(at-MINUTE*i) for i in range(60)]
        keys = ('temperatureC', 'humidityPercent', 'windSpeedMs', 'pressureHpa')
        if any(row is None or any(row[k] is None for k in keys) for row in samples):
            raise LiveSourceError('KMA_PET_HOURLY_WEATHER_MISSING')
        mean = {k: sum(float(row[k]) for row in samples)/60 for k in keys}
        calculated = formula.hourly(mean['temperatureC'], mean['humidityPercent'], mean['windSpeedMs'],
                                    mean['pressureHpa'], metadata['windHeightM'], value, clear, ratio)
        hours[at] = {'observationEnd': at.isoformat(), 'appliesFrom': max(at, start).isoformat(),
                     'appliesUntil': min(at+HOUR, end).isoformat(), 'meanWeather': mean,
                     'solarRadiationMjM2': value, 'radiationBasis': 'ASTRONOMICAL_NIGHT_ZERO' if clear == 0 else 'OBSERVED',
                     'nightCloudReferenceEnd': cloud[0].isoformat() if clear == 0 else None,
                     **solar, **calculated}
    rates = []
    cursor = start
    while cursor < end:
        hour = cursor.astimezone(KST).replace(minute=0, second=0, microsecond=0)
        if hour not in hours:
            raise LiveSourceError('KMA_PET_REQUIRED_HOUR_MISSING')
        rates.append(hours[hour]['referenceEtMmHour']*24)
        cursor += MINUTE
    return {'method': METHOD, 'ratesMmDay': rates, 'hours': list(hours.values()), 'station': metadata,
            'evidence': 'DERIVED_REFERENCE_GRASS_ET_NOT_SITE_MEASUREMENT',
            'timePolicy': 'LAST_COMPLETED_HOUR_HELD_OVER_NEXT_HOUR', 'references': [formula.REFERENCE, formula.METEOROLOGY_REFERENCE],
            'assumptions': ['서울 108 지점의 기상 대표성 미검증', '기준 잔디 증발산을 시설 잠재 증발 입력으로 적용; 재료별 보정 없음',
                            '야간 구름비는 이전 일몰 2~3시간 전 관측에서 파생', '구름비 0.3~1 범위 및 음수 증발산 0 제한',
                            '직전 완료 시간 평균의 다음 시간 유지; 분별 기상 실측을 뜻하지 않음']}


def observed_evaporation(start, end, key):
    if (start.utcoffset() is None or end.utcoffset() is None or start.second or end.second
            or start.microsecond or end.microsecond or not 0 < (end-start).total_seconds() <= 23*3600):
        raise LiveSourceError('KMA_PET_RANGE_INVALID')
    first = start.astimezone(KST).replace(minute=0)
    last = (end-MINUTE).astimezone(KST).replace(minute=0)
    lookback = first-timedelta(hours=36)
    sources, stations = [], []
    for at in (lookback, last):
        raw, meta = fetch(STATION_URL, {'inf': 'AWS', 'stn': '108', 'tm': at.strftime('%Y%m%d%H%M'), 'help': '1'}, key)
        stations.append(station(raw))
        sources.append((raw, meta))
    if stations[0] != stations[1]:
        raise LiveSourceError('KMA_PET_STATION_CHANGED')
    raw, meta = fetch(HOURLY_URL, {'tm1': lookback.strftime('%Y%m%d%H%M'), 'tm2': last.strftime('%Y%m%d%H%M'),
                                  'stn': '108', 'help': '1'}, key)
    sources.append((raw, meta))
    radiation = radiation_rows(raw, lookback, last)
    weather_start = first-HOUR+MINUTE
    weather, cursor = {}, weather_start
    while cursor <= last:
        limit = min(last, cursor+timedelta(hours=6)-MINUTE)
        raw, meta = fetch_range('108', cursor, limit, key)
        sources.append((raw, meta))
        weather.update(meteorology(raw, cursor, limit))
        cursor = limit+MINUTE
    result = derive(start, end, stations[0], radiation, weather)
    result['sourceHashes'] = [meta['sha256'] for _, meta in sources]
    result['sourceRequests'] = [meta for _, meta in sources]
    result['implementationHashes'] = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (Path(__file__), Path(formula.__file__))}
    return result, sources



def reusable_observation_hour(previous, start, end):
    """이미 계산한 완료 시간의 적용 구간 안에서만 같은 증발산 입력 유지."""
    if (not previous or previous.get('method') != METHOD or not previous.get('hours')
            or start.utcoffset() is None or end.utcoffset() is None
            or start.second or end.second or start.microsecond or end.microsecond or end <= start):
        return None
    hour = previous['hours'][-1]
    try:
        observed = datetime.fromisoformat(hour['observationEnd'])
        covered = datetime.fromisoformat(hour['appliesUntil'])
        rate = float(hour['referenceEtMmHour'])*24
        if (covered != start or not observed <= start < end <= observed+HOUR
                or not math.isfinite(rate) or not 0 <= rate <= 100):
            return None
    except (KeyError,TypeError,ValueError):
        return None
    # 강우 최신 조회와 별개로 이미 고정한 기상 입력의 다음 시간 유지 규칙을 적용한다.
    return previous | {'ratesMmDay': [rate]*int((end-start).total_seconds()/60),
        'hours': [hour | {'appliesFrom': start.isoformat(), 'appliesUntil': end.isoformat()}],
        'sourceHashes': [], 'sourceRequests': []}


def append_hours(previous, extension):
    hours = [dict(hour) for hour in previous]
    basis = lambda hour: {key:value for key,value in hour.items() if key not in ('appliesFrom','appliesUntil')}
    for hour in extension:
        if (hours and basis(hours[-1]) == basis(hour)
                and datetime.fromisoformat(hours[-1]['appliesUntil']) == datetime.fromisoformat(hour['appliesFrom'])):
            hours[-1]['appliesUntil'] = hour['appliesUntil']
        else:
            hours.append(dict(hour))
    return hours


def append_evaporation(previous, count, old_rate, extension):
    if previous is not None and len(previous['ratesMmDay']) != count:
        raise ValueError('LIVE_PREVIOUS_PET_INVALID')
    # 이전 계산의 고정 증발 조건도 보존해 새 입력 연결 시 토양 상태가 소급 변경되지 않게 한다.
    old = previous or {'ratesMmDay': [old_rate]*count, 'hours': [], 'sourceHashes': [], 'legacyPrefixMinutes': count}
    return extension | {'ratesMmDay': old['ratesMmDay']+extension['ratesMmDay'],
                        'hours': append_hours(old['hours'],extension['hours']),
                        'sourceHashes': list(dict.fromkeys(old['sourceHashes']+extension['sourceHashes'])),
                        'sourceRequests': old.get('sourceRequests', [])+extension.get('sourceRequests', []),
                        'legacyPrefixMinutes': old.get('legacyPrefixMinutes', 0)}
