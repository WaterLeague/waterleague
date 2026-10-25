"""절대 시각의 AWS 관측 공유 수집·누적 강우 정규화."""
import hashlib
import math
import sqlite3
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from email.utils import parsedate_to_datetime
from http.client import IncompleteRead
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, build_opener

from .rainfall import RainfallQualityError
from . import request_store

KST = timezone(timedelta(hours=9))
ENDPOINT = 'https://apihub.kma.go.kr/api/typ01/cgi-bin/url/nph-aws2_min'


class LiveSourceError(ValueError):
    def __init__(self, code, *, can_reduce_range=True):
        super().__init__(code)
        self.can_reduce_range = can_reduce_range


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def retry_seconds(value):
    try:
        delay = float(int(value)) if value and value.isascii() and value.isdecimal() else (
            parsedate_to_datetime(value)-datetime.now(timezone.utc)).total_seconds()
        return max(60, delay) if math.isfinite(delay) else 60
    except (ValueError, TypeError, OverflowError):
        return 60


def read_response(endpoint, parameters, key, heartbeat=None):
    key = key.strip()
    if not key:
        raise LiveSourceError('KMA_ACCESS_UNAVAILABLE', can_reduce_range=False)
    if heartbeat is not None: heartbeat()
    try:
        day = request_store.reserve(key, 4_000_000)
        try:
            with build_opener(NoRedirect()).open(
                    endpoint+'?'+urlencode(parameters | {'authKey': key}), timeout=30) as response:
                raw = response.read(4_000_001)
        except HTTPError as error:
            status = error.code
            delay = retry_seconds(error.headers.get('Retry-After') if error.headers else None)
            error.close()
            request_store.block(key, status, delay)
            code = 'KMA_ACCESS_UNAVAILABLE' if status in (401,403) else 'KMA_UNAVAILABLE'
            raise LiveSourceError(code, can_reduce_range=False) from None
        except (OSError, TimeoutError, IncompleteRead):
            request_store.block(key)
            raise LiveSourceError('KMA_UNAVAILABLE', can_reduce_range=False) from None
        if len(raw) > 4_000_000 or key.encode() in raw:
            request_store.block(key)
            raise LiveSourceError('KMA_RESPONSE_INVALID', can_reduce_range=False)
        request_store.settle(key, day, 4_000_000, len(raw))
        return raw
    except (request_store.RequestBlocked, OSError, sqlite3.Error):
        raise LiveSourceError('KMA_REQUEST_BUDGET_BLOCKED', can_reduce_range=False) from None


def shared_response(endpoint, parameters, key, heartbeat=None):
    try:
        return request_store.acquire(endpoint, parameters, key,
            lambda: read_response(endpoint, parameters, key, heartbeat), heartbeat,
            ttl=request_store.response_ttl(parameters))
    except (request_store.RequestBlocked, OSError, sqlite3.Error):
        raise LiveSourceError('KMA_REQUEST_BUDGET_BLOCKED', can_reduce_range=False) from None


def canonical_range(start, end, now=None):
    now = now or datetime.now(timezone.utc)
    # 같은 지점의 선행 구간을 공유하되 계산에는 요청한 시각의 관측만 전달한다.
    width = 21600 if end-start <= timedelta(hours=6) else 3600
    first = datetime.fromtimestamp(int(start.timestamp())//width*width, timezone.utc)
    last = datetime.fromtimestamp((int(end.timestamp())+width-1)//width*width, timezone.utc)
    if last > now-timedelta(minutes=2):
        last = end
        common = datetime.fromtimestamp(int(end.timestamp())//21600*21600-21600, timezone.utc)
        if start >= common: first = common
    if last-first > timedelta(days=1): return start, end
    return first, last


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


def observed_zero_intervals(rows):
    minute = timedelta(minutes=1)
    recovered = {}
    previous = None
    for at, row in sorted(rows.items()):
        value = row['dayMm']
        if value is None:
            continue
        if previous is not None:
            before, counter = previous
            local = before.astimezone(KST)
            gap = int((at-before).total_seconds()/60)
            # 같은 날의 누적 관측 총량이 같을 때만 결측 구간의 무강우를 확정한다.
            if (1 < gap <= 360 and local.date() == at.astimezone(KST).date()
                    and (local.hour != 0 or local.minute != 0) and counter == value):
                for n in range(1, gap+1):
                    recovered[before+n*minute] = 'OBSERVED_ZERO_COUNTER_GAP'
        previous = at, value
    for at, row in sorted(rows.items()):
        for size, key in ((15, 'fifteenMinuteMm'), (60, 'sixtyMinuteMm')):
            if row[key] == 0:
                for n in range(size):
                    recovered.setdefault(at-n*minute, 'OBSERVED_ZERO_ROLLING_WINDOW')
    return recovered


def normalized(rows, start, end, allow_gaps=False, rolling_warnings=None, interval_averages=None, verified_zero_gaps=False):
    derived = {}
    methods = {}
    minute = timedelta(minutes=1)
    if rolling_warnings is not None:
        previous_counter = None
        for at, row in sorted(rows.items()):
            if row['dayMm'] is None:
                continue
            if previous_counter is not None:
                before, value = previous_counter
                local = before.astimezone(KST)
                gap = int((at-before).total_seconds()/60)
                # 같은 날의 동일 누적값은 중간 구간 총강우 0의 근거. 양의 차이는 별도 구간 총량 처리로 분리한다.
                midnight_zero = (local.hour == 0 and local.minute == 0 and gap <= 60
                    and local.date() == at.astimezone(KST).date() and row['dayMm'] == 0)
                if midnight_zero:
                    for index in range(1, gap+1):
                        instant = before+minute*index
                        derived[instant], methods[instant] = Decimal(0), 'OBSERVED_ZERO_COUNTER_GAP'
                elif (1 < gap <= 60 and local.date() == at.astimezone(KST).date()
                        and (local.hour != 0 or local.minute != 0) and value == row['dayMm']):
                    for index in range(1, gap+1):
                        instant = before+minute*index
                        derived[instant], methods[instant] = Decimal(0), 'OBSERVED_ZERO_COUNTER_GAP'
                elif (interval_averages is not None and 1 < gap <= 360
                        and local.date() == at.astimezone(KST).date()
                        and (local.hour != 0 or local.minute != 0)
                        and 0 < row['dayMm']-value <= Decimal(100)*gap):
                    total = row['dayMm']-value
                    # 관측 구간 총량만 보존. 구간 내부 분배는 평균 강도의 모델 가정으로 별도 기록.
                    for index in range(1, gap+1):
                        instant = before+minute*index
                        derived[instant], methods[instant] = total/Decimal(gap), 'OBSERVED_INTERVAL_MEAN_ASSUMPTION'
                    if start < at <= end:
                        interval_averages.append({'start':before.isoformat(),'end':at.isoformat(),
                            'minutes':gap,'totalMm':float(total),'timeDistribution':'UNIFORM_NOT_MINUTE_OBSERVATIONS'})
            previous_counter = at, row['dayMm']
    if rolling_warnings is not None:
        for at, row in sorted(rows.items()):
            local = at.astimezone(KST)
            previous, following = rows.get(at-minute), rows.get(at+minute)
            if (local.hour == 0 and local.minute == 0 and previous and following
                    and row['fifteenMinuteMm'] is None and row['sixtyMinuteMm'] is None
                    and all(r['dayMm'] is not None for r in (previous,row,following))
                    and 0 <= row['dayMm'] <= 100 and previous['dayMm'] > row['dayMm']
                    and 0 <= following['dayMm']-row['dayMm'] <= 100):
                # 구형 장비의 00:00 누적 초기화는 양옆 누적 관측으로 판별하고 별도 기록한다.
                derived[at], methods[at] = row['dayMm'], 'OBSERVED_MIDNIGHT_COUNTER_RESET'
                derived[at+minute], methods[at+minute] = following['dayMm']-row['dayMm'], 'OBSERVED_MIDNIGHT_COUNTER_RESET'
                if start < at <= end:
                    rolling_warnings.append({'at':at.isoformat(),'midnightResetInferred':True})
    zero_intervals = observed_zero_intervals(rows) if verified_zero_gaps else {}
    if verified_zero_gaps:
        for at, method in zero_intervals.items():
            if at not in derived:
                derived[at], methods[at] = Decimal(0), method
    for at, current in sorted(rows.items()):
        previous = rows.get(at-minute)
        if previous is None:
            continue
        local = at.astimezone(KST)
        boundary = local.hour == 0 and local.minute in (0, 1)
        if not boundary and current['dayMm'] is not None and previous['dayMm'] is not None:
            difference = current['dayMm']-previous['dayMm']
            if not 0 <= difference <= 100:
                if rolling_warnings is None: raise RainfallQualityError('AWS_CUMULATIVE_REVERSED')
                rolling_warnings.append({'at':at.isoformat(),'counterRevisionMm':float(difference),'policy':'ROLLING_OBSERVATION_REQUIRED'})
            else:
                derived[at], methods[at] = difference, 'DAILY_DIFFERENCE'
        for size, key in ((15, 'fifteenMinuteMm'), (60, 'sixtyMinuteMm')):
            window = [derived.get(at-i*minute) for i in range(1, size)]
            if current[key] is None or any(value is None for value in window):
                continue
            difference = current[key]-sum(window)
            if (boundary or rolling_warnings is not None) and at not in derived:
                if not 0 <= difference <= 100:
                    if rolling_warnings is not None: continue
                    raise RainfallQualityError('AWS_MIDNIGHT_INVALID')
                derived[at], methods[at] = difference, f'ROLLING_{size}_MINUTE_DIFFERENCE'
            if at in derived and abs(derived[at]-difference) > Decimal('.1'):
                if rolling_warnings is None:
                    raise RainfallQualityError('AWS_ROLLING_TOTAL_MISMATCH')
                if start < at <= end:
                    rolling_warnings.append({'at': at.isoformat(), 'windowMinutes': size,
                        'counterDepthMm': float(derived[at]), 'rollingDerivedDepthMm': float(difference)})
    if any(derived.get(at, Decimal(0)) != 0 for at in zero_intervals):
        raise RainfallQualityError('AWS_ROLLING_TOTAL_MISMATCH')
    if rolling_warnings is not None:
        for at, row in sorted(rows.items()):
            for size, key in ((15, 'fifteenMinuteMm'), (60, 'sixtyMinuteMm')):
                if row[key] != 0:
                    continue
                instants = [at-i*minute for i in range(size)]
                if any(derived.get(t,Decimal(0)) != 0 for t in instants):
                    continue
                for t in instants:
                    if t not in derived:
                        derived[t], methods[t] = Decimal(0), 'OBSERVED_ZERO_ROLLING_WINDOW'
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
                           k: float(v) if v is not None else None for k, v in rows.get(at, {}).items()
                           if k in ('temperatureC', 'humidityPercent', 'windSpeedMs', 'pressureHpa')}})
        at += minute
    if (not result and not allow_gaps) or at != end+minute:
        raise RainfallQualityError('AWS_INTERVAL_INVALID')
    return result


def fetch_range(station, start, end, key, heartbeat=None, canonical=False):
    if not key:
        raise LiveSourceError('KMA_ACCESS_UNAVAILABLE')
    if (not station.isdigit() or not 1 <= len(station) <= 5 or start.utcoffset() is None
            or end.utcoffset() is None or start.second or end.second or start.microsecond
            or end.microsecond or not 0 < (end-start).total_seconds() <= 86400):
        raise LiveSourceError('KMA_RANGE_INVALID')
    if canonical: start, end = canonical_range(start, end)
    parameters = {'tm1': start.astimezone(KST).strftime('%Y%m%d%H%M'),
                  'tm2': end.astimezone(KST).strftime('%Y%m%d%H%M'),
                  'stn': station, 'disp': '0', 'help': '1'}
    raw, acquisition = shared_response(ENDPOINT, parameters, key, heartbeat)
    return raw, {'provider': 'KMA_AWS_DIRECT', 'endpoint': ENDPOINT, 'parameters': parameters,
                 'fetchedAt': acquisition['fetchedAt'],
                 **({'responseStart': start.isoformat(), 'responseEnd': end.isoformat()} if canonical else {}),
                 'sha256': hashlib.sha256(raw).hexdigest(), 'purpose': 'SIMULATION_USED_INPUT_ONLY'}


def observed_forcing(station, start, end, key, chunk_hours=23, antecedent_quality=False, heartbeat=None, allow_gaps=False, share_ranges=False, verified_zero_gaps=False):
    if not isinstance(chunk_hours, int) or not 1 <= chunk_hours <= 23:
        raise LiveSourceError('KMA_RANGE_INVALID')
    cursor = start-timedelta(minutes=61)
    rows, sources = {}, []
    hours = min(chunk_hours, math.ceil((end-cursor).total_seconds()/3600))
    while cursor < end:
        if heartbeat is not None: heartbeat()
        while True:
            limit = min(end, cursor+timedelta(hours=hours))
            if share_ranges and hours >= 6:
                boundary = datetime.fromtimestamp((int(cursor.timestamp())//21600+1)*21600, timezone.utc)
                limit = min(limit, boundary)
            try:
                raw, meta = fetch_range(station, cursor, limit, key, heartbeat=heartbeat, **({'canonical': True} if share_ranges else {}))
                break
            except LiveSourceError as error:
                if str(error) != 'KMA_UNAVAILABLE' or not error.can_reduce_range or hours == 1: raise
                hours = max(1,hours//2)
        first = datetime.fromisoformat(meta['responseStart']) if 'responseStart' in meta else cursor
        last = datetime.fromisoformat(meta['responseEnd']) if 'responseEnd' in meta else limit
        values = {at: row for at,row in parse(raw, station, first, last).items() if cursor <= at <= limit}
        for at, value in values.items():
            if at in rows and rows[at] != value:
                raise RainfallQualityError('AWS_OVERLAPPING_RESPONSE_CHANGED')
            rows[at] = value
        sources.append((raw, meta))
        cursor = limit
    warnings = [] if antecedent_quality else None
    intervals = [] if antecedent_quality else None
    observations = normalized(rows, start, end, allow_gaps=allow_gaps, rolling_warnings=warnings, interval_averages=intervals, verified_zero_gaps=verified_zero_gaps)
    return {'stationId': station, 'start': start.isoformat(), 'end': end.isoformat(),
            'intervalSeconds': 60, 'observations': observations,
            'overlapObservations': normalized(rows, start-timedelta(minutes=60), start, allow_gaps=True, rolling_warnings=warnings, verified_zero_gaps=verified_zero_gaps),
            **({'observationRecoveryPolicy': 'OBSERVED_ZERO_TOTALS_ONLY_V1'} if verified_zero_gaps else {}),
            **({'qualityWarnings': warnings, 'qualityPolicy': 'ANTECEDENT_DAILY_COUNTER_PRIMARY_ROLLING_CHECK_RECORDED', 'aggregatedRainIntervals': intervals} if antecedent_quality else {}),
            'sourceHashes': [meta['sha256'] for _, meta in sources],
            'evidence': 'OBSERVED_AWS_DERIVED_INTERVAL_DEPTH'}, sources
