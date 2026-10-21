"""선행 상태의 AWS 결측만 사전 고정한 서울시 10분 관측으로 보강."""
import hashlib
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlencode
from urllib.error import HTTPError
from urllib.request import Request, build_opener

from .live import KST, NoRedirect, LiveSourceError
from .rainfall import RainfallQualityError
from . import request_store

ROOT = Path(__file__).resolve().parents[3]
REGISTRY = ROOT / 'backend/src/main/resources/native-weather/v1/antecedent-fallback.json'
ENDPOINT = 'https://datafile.seoul.go.kr/bigfile/iot/sheet/json/download.do'
DOCUMENTATION = 'https://data.seoul.go.kr/dataList/OA-23092/S/1/datasetView.do'
LIMIT = 8_000_000


def fetch(station, heartbeat=None):
    if not isinstance(station, str) or not station.isdigit() or len(station) > 5:
        raise LiveSourceError('SEOUL_RAIN_STATION_INVALID')
    parameters = {'srvType': 'S', 'infId': 'OA-23092', 'serviceKind': '0', 'pageNo': '1',
        'ssUserId': 'SAMPLE_VIEW', 'strWhere': '', 'strOrderby': 'DATA_CLCT_TM DESC',
        'filterCol': 'RF_CD', 'txtFilter': station, 'gridTotalCnt': '0'}
    def retrieve():
        if heartbeat is not None: heartbeat()
        day = request_store.reserve('PUBLIC', LIMIT, provider='SEOUL_RAIN', max_calls=1000, max_bytes=1_000_000_000)
        try:
            request = Request(ENDPOINT, data=urlencode(parameters).encode(), headers={'Referer': DOCUMENTATION})
            with build_opener(NoRedirect()).open(request, timeout=25) as response:
                raw = response.read(LIMIT+1)
            if len(raw)>LIMIT: raise LiveSourceError('SEOUL_RAIN_RESPONSE_TOO_LARGE')
        except HTTPError as error:
            status = error.code
            from .live import retry_seconds
            delay = retry_seconds(error.headers.get('Retry-After') if error.headers else None)
            error.close()
            request_store.block('PUBLIC', status, delay, provider='SEOUL_RAIN')
            raise LiveSourceError('SEOUL_RAIN_UNAVAILABLE') from None
        except Exception:
            request_store.block('PUBLIC', provider='SEOUL_RAIN')
            raise LiveSourceError('SEOUL_RAIN_UNAVAILABLE') from None
        request_store.settle('PUBLIC', day, LIMIT, len(raw), provider='SEOUL_RAIN')
        return raw
    try:
        raw, acquisition = request_store.acquire(ENDPOINT, parameters, 'PUBLIC', retrieve,
            heartbeat, ttl=600, provider='SEOUL_RAIN')
    except Exception:
        raise LiveSourceError('SEOUL_RAIN_UNAVAILABLE') from None
    if heartbeat is not None: heartbeat()
    return raw, {'provider': 'SEOUL_OPEN_DATA_DIRECT', 'endpoint': ENDPOINT,
        'parameters': parameters, 'method': 'POST', 'documentationUrl': DOCUMENTATION,
        'fetchedAt': acquisition['fetchedAt'],
        'sha256': hashlib.sha256(raw).hexdigest(), 'purpose': 'ANTECEDENT_GAP_SUPPLEMENT_ONLY',
        'license': 'KOGL_TYPE_2_ATTRIBUTION_NONCOMMERCIAL'}


def parse(raw, binding, start, end):
    try:
        if len(raw) > LIMIT:
            raise ValueError()
        records = json.loads(raw)['DATA']
        if not isinstance(records, list) or not 0 < len(records) <= 50000:
            raise ValueError()
        intervals = {}
        for row in records:
            # 공식 다운로드의 코드 검색은 부분 일치여서 정확한 코드로 다시 한정한다.
            if str(row['rf_cd']) != binding['stationId']:
                continue
            if (row['rf_nm'] != binding['name']
                    or row['gu_nm'] != binding['districtName']):
                raise ValueError()
            label = datetime.strptime(row['data_clct_tm'], '%Y-%m-%d %H:%M').replace(tzinfo=KST)
            if label.strftime('%Y-%m-%d %H:%M') != row['data_clct_tm'] or label.minute % 10 != 9:
                raise ValueError()
            right = label + timedelta(minutes=1)
            if right <= start or right-timedelta(minutes=10) >= end:
                continue
            # 구간 종료 뒤의 관측은 선행 상태에 섞지 않는다.
            if right > end:
                continue
            depth = Decimal(str(row['rn_10m']))
            if right in intervals or not depth.is_finite() or not 0 <= depth <= 1000:
                raise ValueError()
            intervals[right] = depth
        return intervals
    except (KeyError, TypeError, ValueError, UnicodeError, InvalidOperation):
        raise RainfallQualityError('SEOUL_RAIN_SOURCE_INVALID') from None


def supplement(rain, start, end, fetcher=None, heartbeat=None):
    minute = timedelta(minutes=1)
    expected = int((end-start).total_seconds()/60)
    existing = {datetime.fromisoformat(row['end']): row for row in rain['observations']}
    if len(existing) != len(rain['observations']):
        raise RainfallQualityError('AWS_DUPLICATE_INTERVAL')
    missing = [start+minute*i for i in range(1, expected+1) if start+minute*i not in existing]
    if not missing:
        return rain, []
    registry_raw = REGISTRY.read_bytes()
    registry = json.loads(registry_raw)
    if start < datetime.fromisoformat(registry['effectiveFromKst']):
        raise RainfallQualityError('SEOUL_RAIN_LOCATION_PERIOD_UNSUPPORTED')
    binding = registry['bindings'].get(rain['stationId'])
    if binding is None:
        raise RainfallQualityError('SEOUL_RAIN_BINDING_UNAVAILABLE')
    raw, metadata = (fetcher or fetch)(binding['secondary']['stationId'], heartbeat=heartbeat)
    if hashlib.sha256(raw).hexdigest() != metadata['sha256']:
        raise RainfallQualityError('SEOUL_RAIN_SOURCE_HASH_INVALID')
    intervals = parse(raw, binding['secondary'], start, end)
    applied = {}
    for at in missing:
        local = at.astimezone(KST)
        right = local.replace(minute=local.minute-local.minute % 10) + (
            timedelta(minutes=10) if local.minute % 10 else timedelta())
        if right not in intervals:
            raise RainfallQualityError('SEOUL_RAIN_REQUIRED_INTERVAL_MISSING')
        total = intervals[right]
        # 양의 10분 총량은 평균 강도 가정이며 실제 분 관측으로 표시하지 않는다.
        existing[at] = {'end': at.isoformat(), 'depthMm': float(total/10),
            'method': 'SEOUL_NEAREST_10M_MEAN_ASSUMPTION' if total else 'SEOUL_NEAREST_10M_ZERO_ASSUMPTION',
            'weather': {}}
        applied.setdefault(right, []).append(at)
    records = [{'start': (right-timedelta(minutes=10)).isoformat(), 'end': right.isoformat(),
        'secondaryTotalMm': float(intervals[right]), 'appliedMinutes': len(instants),
        'appliedMinuteEnds': [at.isoformat() for at in instants],
        'appliedDepthMm': float(intervals[right]*len(instants)/10),
        'timeDistribution': 'UNIFORM_10M_NOT_MINUTE_OBSERVATIONS'} for right, instants in sorted(applied.items())]
    registry_meta = {'provider': 'FROZEN_STATION_SELECTION', 'sha256': hashlib.sha256(registry_raw).hexdigest(),
        'purpose': 'ANTECEDENT_GAP_SUPPLEMENT_ONLY', 'file': str(REGISTRY.relative_to(ROOT))}
    result = rain | {'observations': [existing[start+minute*i] for i in range(1, expected+1)],
        'sourceHashes': rain['sourceHashes'] + [metadata['sha256'], registry_meta['sha256']],
        'evidence': 'AWS_OBSERVATIONS_WITH_SEOUL_NEAREST_GAUGE_GAP_ASSUMPTION',
        'qualityPolicy': 'AWS_PRIMARY_FIXED_NEAREST_SEOUL_10M_ANTECEDENT_V1',
        'supplement': {'binding': binding, 'selectionVersion': registry['version'],
            'sourceSha256': metadata['sha256'], 'registrySha256': registry_meta['sha256'],
            'minutes': len(missing), 'fraction': len(missing)/expected, 'intervals': records,
            'assumptions': ['인접 관측소의 강우를 AWS 결측 구간에 대용; 부지 강우 대표성 미검증',
                '10분 총량의 균일 분배; 정상 AWS 분 관측 유지; 완결되지 않은 구간 제외']}}
    return result, [(raw, metadata), (registry_raw, registry_meta)]
