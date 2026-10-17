"""계산에 필요한 AWS 구간의 직접 조회·누적 강우 정규화. 최신 조회용 저장소 없음."""
import hashlib
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, build_opener

from .rainfall import RainfallQualityError

KST = timezone(timedelta(hours=9))
ENDPOINT = 'https://apihub.kma.go.kr/api/typ01/cgi-bin/url/nph-aws2_min'


class LiveSourceError(ValueError):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def number(value, minimum, maximum):
    try:
        n = Decimal(value)
        if not n.is_finite():
            raise ValueError()
        if n <= -99 or minimum >= 0 and n <= -50:
            return None
        if not minimum <= n <= maximum:
            raise ValueError()
        return n
    except (InvalidOperation, ValueError):
        raise RainfallQualityError('AWS_VALUE_INVALID') from None


def parse(raw, station, start, end):
    try:
        text = raw.decode('utf-8')
        if (not text.startswith('#START7777') or not text.strip().endswith('#7777END')
                or 'RN-15m RN-60m RN-12H RN-DAY' not in text):
            raise ValueError()
        rows = {}
        for line in text.splitlines():
            if not line.strip() or line.startswith('#'):
                continue
            f = line.split()
            if len(f) != 18 or f[1] != station:
                raise ValueError()
            at = datetime.strptime(f[0], '%Y%m%d%H%M').replace(tzinfo=KST).astimezone(timezone.utc)
            if at in rows or not start <= at <= end:
                raise ValueError()
            rows[at] = {
                'fifteenMinuteMm': number(f[10], 0, 5000),
                'sixtyMinuteMm': number(f[11], 0, 5000), 'dayMm': number(f[13], 0, 5000),
                'temperatureC': number(f[8], -90, 60), 'humidityPercent': number(f[14], 0, 100),
                'windSpeedMs': number(f[7], 0, 150), 'pressureHpa': number(f[15], 300, 1100)}
        return rows
    except (UnicodeError, ValueError):
        raise RainfallQualityError('AWS_SOURCE_INVALID') from None


def normalized(rows, start, end, allow_gaps=False):
    derived = {}
    methods = {}
    minute = timedelta(minutes=1)
    for at, current in sorted(rows.items()):
        previous = rows.get(at-minute)
        if previous is None:
            continue
        local = at.astimezone(KST)
        boundary = local.hour == 0 and local.minute in (0, 1)
        if not boundary and current['dayMm'] is not None and previous['dayMm'] is not None:
            difference = current['dayMm']-previous['dayMm']
            if not 0 <= difference <= 100:
                raise RainfallQualityError('AWS_CUMULATIVE_REVERSED')
            derived[at], methods[at] = difference, 'DAILY_DIFFERENCE'
        for size, key in ((15, 'fifteenMinuteMm'), (60, 'sixtyMinuteMm')):
            window = [derived.get(at-i*minute) for i in range(1, size)]
            if current[key] is None or any(value is None for value in window):
                continue
            difference = current[key]-sum(window)
            if boundary and at not in derived:
                if not 0 <= difference <= 100:
                    raise RainfallQualityError('AWS_MIDNIGHT_INVALID')
                derived[at], methods[at] = difference, f'ROLLING_{size}_MINUTE_DIFFERENCE'
            if at in derived and abs(derived[at]-difference) > Decimal('.1'):
                raise RainfallQualityError('AWS_ROLLING_TOTAL_MISMATCH')
    result = []
    at = start+minute
    while at <= end:
        if at not in derived:
            if allow_gaps:
                at += minute
                continue
            raise RainfallQualityError('AWS_REQUIRED_MINUTE_MISSING')
        result.append({'end': at.isoformat(), 'depthMm': float(derived[at]),
                       'method': methods[at], 'weather': {
                           k: float(v) if v is not None else None for k, v in rows[at].items()
                           if k in ('temperatureC', 'humidityPercent', 'windSpeedMs', 'pressureHpa')}})
        at += minute
    if (not result and not allow_gaps) or at != end+minute:
        raise RainfallQualityError('AWS_INTERVAL_INVALID')
    return result


def fetch_range(station, start, end, key):
    if not key:
        raise LiveSourceError('KMA_ACCESS_UNAVAILABLE')
    if (not station.isdigit() or not 1 <= len(station) <= 5 or start.utcoffset() is None
            or end.utcoffset() is None or start.second or end.second or start.microsecond
            or end.microsecond or not 0 < (end-start).total_seconds() <= 86400):
        raise LiveSourceError('KMA_RANGE_INVALID')
    parameters = {'tm1': start.astimezone(KST).strftime('%Y%m%d%H%M'),
                  'tm2': end.astimezone(KST).strftime('%Y%m%d%H%M'),
                  'stn': station, 'disp': '0', 'help': '1'}
    try:
        with build_opener(NoRedirect()).open(ENDPOINT+'?'+urlencode(parameters | {'authKey': key}), timeout=30) as response:
            raw = response.read(4_000_001)
        if len(raw) > 4_000_000 or key.encode() in raw:
            raise LiveSourceError('KMA_RESPONSE_INVALID')
    except HTTPError as e:
        raise LiveSourceError('KMA_ACCESS_UNAVAILABLE' if e.code in (401, 403) else 'KMA_UNAVAILABLE') from None
    except (OSError, TimeoutError):
        raise LiveSourceError('KMA_UNAVAILABLE') from None
    return raw, {'provider': 'KMA_AWS_DIRECT', 'endpoint': ENDPOINT, 'parameters': parameters,
                 'fetchedAt': datetime.now(timezone.utc).isoformat(),
                 'sha256': hashlib.sha256(raw).hexdigest(), 'purpose': 'SIMULATION_USED_INPUT_ONLY'}


def observed_forcing(station, start, end, key):
    cursor = start-timedelta(minutes=61)
    rows, sources = {}, []
    while cursor < end:
        limit = min(end, cursor+timedelta(hours=23))
        raw, meta = fetch_range(station, cursor, limit, key)
        values = parse(raw, station, cursor, limit)
        for at, value in values.items():
            if at in rows and rows[at] != value:
                raise RainfallQualityError('AWS_OVERLAPPING_RESPONSE_CHANGED')
            rows[at] = value
        sources.append((raw, meta))
        cursor = limit
    return {'stationId': station, 'start': start.isoformat(), 'end': end.isoformat(),
            'intervalSeconds': 60, 'observations': normalized(rows, start, end),
            'overlapObservations': normalized(rows, start-timedelta(minutes=60), start, allow_gaps=True),
            'sourceHashes': [meta['sha256'] for _, meta in sources],
            'evidence': 'OBSERVED_AWS_DERIVED_INTERVAL_DEPTH'}, sources
