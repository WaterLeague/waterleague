"""WAMIS 공개 시자료의 눈금 수위 정규화. 영점표고 자동 가산 없음."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re

from waterleague_sim.engine.flood_errors import FloodModelError, require
from waterleague_sim.engine.swmm import ROOT

KST = timezone(timedelta(hours=9))


def normalize(raw, station_id, start_date, end_date):
    require(isinstance(station_id, str) and re.fullmatch(r'\d{7}', station_id), 'WAMIS_STATION_INVALID')
    try:
        first, last = (datetime.strptime(value, '%Y%m%d').replace(tzinfo=KST)
                       for value in (start_date, end_date))
        def unique_pairs(pairs):
            result = {}
            for key, value in pairs:
                require(key not in result, 'WAMIS_DUPLICATE_FIELD')
                result[key] = value
            return result
        payload = json.loads(raw, object_pairs_hook=unique_pairs)
    except (ValueError, TypeError, UnicodeError):
        raise FloodModelError('WAMIS_SOURCE_INVALID') from None
    require(0 <= (last - first).days <= 184 and isinstance(payload, dict)
            and isinstance(payload.get('rows'), list), 'WAMIS_SOURCE_INVALID')
    days, records = set(), []
    for row in payload['rows']:
        require(isinstance(row, dict), 'WAMIS_ROW_INVALID')
        try:
            day = datetime.strptime(row['ymdh'], '%Y-%m-%d').replace(tzinfo=KST)
        except (KeyError, TypeError, ValueError):
            raise FloodModelError('WAMIS_DATE_INVALID') from None
        require(first <= day <= last and day not in days, 'WAMIS_DATE_INVALID')
        days.add(day)
        for hour in range(1, 25):
            require('h' + str(hour) in row, 'WAMIS_HOUR_MISSING')
            value = row['h' + str(hour)]
            missing = value is None or value in ('', '-', '-9999', 'NaN')
            if not missing:
                try:
                    require(type(value) in (str, int, float), 'WAMIS_VALUE_INVALID')
                    number = Decimal(str(value))
                    require(number.is_finite(), 'WAMIS_VALUE_INVALID')
                    missing = number == -9999
                except InvalidOperation:
                    raise FloodModelError('WAMIS_VALUE_INVALID') from None
            instant = day + timedelta(hours=hour)
            records.append({'timeUtc': instant.astimezone(timezone.utc).isoformat(),
                            'gaugeLevelM': None if missing else float(number),
                            'quality': 'MISSING' if missing else 'UNCORRECTED_PUBLIC_VALUE'})
    require(len(days) == (last - first).days + 1, 'WAMIS_DAY_MISSING')
    records.sort(key=lambda row: row['timeUtc'])
    return {'schemaVersion': 1, 'stationId': station_id, 'unit': 'm',
            'reference': 'STATION_GAUGE_NOT_ABSOLUTE_ELEVATION',
            'sourceTimeZone': 'Asia/Seoul', 'hour24MeansNextDayMidnight': True,
            'sourceSha256': hashlib.sha256(raw).hexdigest(),
            'request': {'date1': start_date, 'date2': end_date},
            'sampleCount': len(records), 'missingCount': sum(row['quality'] == 'MISSING' for row in records),
            'records': records, 'rankingEligible': False,
            'limitations': ['실시간 시자료는 검보정 전 자료', '시점별 영점표고 미확인; 절대 수면고 변환 없음']}


def diagnostic_boundary(normalized, start_utc, end_utc):
    from waterleague_sim.forcing.stage import utc
    require(normalized.get('reference') == 'STATION_GAUGE_NOT_ABSOLUTE_ELEVATION',
            'WAMIS_REFERENCE_INVALID')
    start, end = utc(start_utc), utc(end_utc)
    records = normalized['records']
    before = [i for i, row in enumerate(records) if utc(row['timeUtc']) <= start]
    after = [i for i, row in enumerate(records) if utc(row['timeUtc']) >= end]
    require(start < end and before and after, 'WAMIS_WINDOW_INCOMPLETE')
    rows = records[max(before):min(after) + 1]
    require(all(row['quality'] == 'UNCORRECTED_PUBLIC_VALUE' and row['gaugeLevelM'] is not None
                for row in rows), 'WAMIS_WINDOW_HAS_MISSING_VALUES')
    return {'type': 'TIME_SERIES_STAGE', 'unit': 'm', 'interpolation': 'LINEAR',
            'maximumGapSeconds': 3600, 'momentum': 'ZERO_RESERVOIR_ASSUMPTION',
            'referenceStatus': 'LOCAL_DIAGNOSTIC',
            'verticalDatum': 'WAMIS_GAUGE_' + normalized['stationId'] + '_DIAGNOSTIC',
            'evidence': {'sourceSha256': normalized['sourceSha256'],
                         'stationId': normalized['stationId'], 'reference': normalized['reference'],
                         'limitation': '실제 관측의 시간 변화 입력 시험; 실제 지형과 절대 높이 결합 불가'},
            'samples': [{'timeUtc': row['timeUtc'], 'stageM': row['gaugeLevelM']} for row in rows]}


def read_archive(manifest_file, expected_sha256, root=ROOT):
    root = Path(root).resolve()
    def read(relative):
        require(isinstance(relative, str) and not Path(relative).is_absolute()
                and '..' not in Path(relative).parts, 'WAMIS_ARCHIVE_PATH_INVALID')
        path = root / relative
        require(not any(p.is_symlink() for p in (path, *path.parents)) and path.is_file()
                and path.stat().st_size <= 8 * 1024**2, 'WAMIS_ARCHIVE_FILE_INVALID')
        return path.read_bytes()
    raw = read(manifest_file)
    require(hashlib.sha256(raw).hexdigest() == expected_sha256, 'WAMIS_MANIFEST_HASH_MISMATCH')
    try:
        manifest = json.loads(raw)
        require(manifest['schemaVersion'] == 1 and manifest['source'] == 'WAMIS_PUBLIC_HOURLY_TABLE',
                'WAMIS_MANIFEST_INVALID')
        sources = {manifest_file: raw}
        for name, expected in manifest['files'].items():
            value = read(name)
            require(hashlib.sha256(value).hexdigest() == expected, 'WAMIS_SOURCE_HASH_MISMATCH')
            sources[name] = value
        hourly = [value for name, value in sources.items() if Path(name).name == 'hourly.json']
        saved = [value for name, value in sources.items() if Path(name).name == 'normalized.json']
        require(len(hourly) == len(saved) == 1, 'WAMIS_MANIFEST_INVALID')
        result = normalize(hourly[0], manifest['stationId'], manifest['parameters']['date1'],
                           manifest['parameters']['date2'])
        require(result == json.loads(saved[0]), 'WAMIS_NORMALIZATION_MISMATCH')
        return result, sources
    except (KeyError, TypeError, json.JSONDecodeError):
        raise FloodModelError('WAMIS_MANIFEST_INVALID') from None
