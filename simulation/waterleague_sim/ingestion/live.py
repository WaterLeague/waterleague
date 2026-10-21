"""계산에 필요한 AWS 구간의 직접 조회·누적 강우 정규화. 최신 조회용 저장소 없음."""
import hashlib
import math
import random
import ssl
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from email.utils import parsedate_to_datetime
from http.client import IncompleteRead
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, build_opener

from .rainfall import RainfallQualityError

KST = timezone(timedelta(hours=9))
ENDPOINT = 'https://apihub.kma.go.kr/api/typ01/cgi-bin/url/nph-aws2_min'


class LiveSourceError(ValueError):
    def __init__(self, code, *, can_reduce_range=True):
        super().__init__(code)
        self.can_reduce_range = can_reduce_range


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def retry_delay(value):
    if value is None:
        return random.uniform(.5, 1)
    try:
        delay = float(int(value)) if value.isascii() and value.isdecimal() else (
            parsedate_to_datetime(value)-datetime.now(timezone.utc)).total_seconds()
        return max(0, delay) if math.isfinite(delay) and delay <= 2 else None
    except (ValueError, TypeError, OverflowError):
        return None


def read_response(endpoint, parameters, key, heartbeat=None):
    for attempt in range(2):
        if heartbeat is not None:
            heartbeat()
        delay, reduce_range = None, True
        try:
            with build_opener(NoRedirect()).open(
                    endpoint+'?'+urlencode(parameters | {'authKey': key}), timeout=30) as response:
                raw = response.read(4_000_001)
            if len(raw) > 4_000_000 or key.encode() in raw:
                raise LiveSourceError('KMA_RESPONSE_INVALID')
            return raw
        except HTTPError as error:
            status = error.code
            retry_after = error.headers.get('Retry-After') if error.headers else None
            error.close()
            if status in (401, 403):
                raise LiveSourceError('KMA_ACCESS_UNAVAILABLE') from None
            if status in (408, 429, 500, 502, 503, 504):
                delay = retry_delay(retry_after)
            # 서버 대기 지시·호출 제한을 구간 분할 요청으로 우회하지 않는다.
            reduce_range = status != 429 and retry_after is None and delay is not None
        except (OSError, TimeoutError, IncompleteRead) as error:
            if isinstance(getattr(error, 'reason', error), ssl.SSLCertVerificationError):
                reduce_range = False
            else:
                delay = retry_delay(None)
        if attempt or delay is None:
            raise LiveSourceError('KMA_UNAVAILABLE', can_reduce_range=reduce_range) from None
        if heartbeat is not None:
            heartbeat()
        time.sleep(delay)


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


def normalized(rows, start, end, allow_gaps=False, rolling_warnings=None, interval_averages=None):
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


def fetch_range(station, start, end, key, heartbeat=None):
    if not key:
        raise LiveSourceError('KMA_ACCESS_UNAVAILABLE')
    if (not station.isdigit() or not 1 <= len(station) <= 5 or start.utcoffset() is None
            or end.utcoffset() is None or start.second or end.second or start.microsecond
            or end.microsecond or not 0 < (end-start).total_seconds() <= 86400):
        raise LiveSourceError('KMA_RANGE_INVALID')
    parameters = {'tm1': start.astimezone(KST).strftime('%Y%m%d%H%M'),
                  'tm2': end.astimezone(KST).strftime('%Y%m%d%H%M'),
                  'stn': station, 'disp': '0', 'help': '1'}
    raw = read_response(ENDPOINT, parameters, key, heartbeat)
    return raw, {'provider': 'KMA_AWS_DIRECT', 'endpoint': ENDPOINT, 'parameters': parameters,
                 'fetchedAt': datetime.now(timezone.utc).isoformat(),
                 'sha256': hashlib.sha256(raw).hexdigest(), 'purpose': 'SIMULATION_USED_INPUT_ONLY'}


def observed_forcing(station, start, end, key, chunk_hours=23, antecedent_quality=False, heartbeat=None, allow_gaps=False):
    if not isinstance(chunk_hours, int) or not 1 <= chunk_hours <= 23:
        raise LiveSourceError('KMA_RANGE_INVALID')
    cursor = start-timedelta(minutes=61)
    rows, sources = {}, []
    hours = min(chunk_hours, math.ceil((end-cursor).total_seconds()/3600))
    while cursor < end:
        if heartbeat is not None: heartbeat()
        while True:
            limit = min(end, cursor+timedelta(hours=hours))
            try:
                raw, meta = fetch_range(station, cursor, limit, key, heartbeat=heartbeat)
                break
            except LiveSourceError as error:
                if str(error) != 'KMA_UNAVAILABLE' or not error.can_reduce_range or hours == 1: raise
                hours = max(1,hours//2)
        values = parse(raw, station, cursor, limit)
        for at, value in values.items():
            if at in rows and rows[at] != value:
                raise RainfallQualityError('AWS_OVERLAPPING_RESPONSE_CHANGED')
            rows[at] = value
        sources.append((raw, meta))
        cursor = limit
    warnings = [] if antecedent_quality else None
    intervals = [] if antecedent_quality else None
    observations = normalized(rows, start, end, allow_gaps=allow_gaps, rolling_warnings=warnings, interval_averages=intervals)
    return {'stationId': station, 'start': start.isoformat(), 'end': end.isoformat(),
            'intervalSeconds': 60, 'observations': observations,
            'overlapObservations': normalized(rows, start-timedelta(minutes=60), start, allow_gaps=True, rolling_warnings=warnings),
            **({'qualityWarnings': warnings, 'qualityPolicy': 'ANTECEDENT_DAILY_COUNTER_PRIMARY_ROLLING_CHECK_RECORDED', 'aggregatedRainIntervals': intervals} if antecedent_quality else {}),
            'sourceHashes': [meta['sha256'] for _, meta in sources],
            'evidence': 'OBSERVED_AWS_DERIVED_INTERVAL_DEPTH'}, sources
