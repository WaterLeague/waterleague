"""서울시 10분 누적 강우의 원시 시각 보존·완전 구간 검사."""
import csv
import io
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

from .rainfall import RainInterval, RainfallQualityError, require_complete

KST = timezone(timedelta(hours=9))
STEP = timedelta(minutes=10)
QUALITY = frozenset({'BASIC_CHECKED_UNCORRECTED'})


@dataclass(frozen=True)
class SeoulRainRecord:
    label: datetime
    depth: Decimal
    line: int


def parse(text: str, station_name: str) -> list[SeoulRainRecord]:
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames != ['강우량계명', '시간', '10분우량']:
        raise RainfallQualityError('서울 강우 필드 불일치')
    result = []
    for line, row in enumerate(reader, start=2):
        if None in row or any(value is None for value in row.values()) or row['강우량계명'] != station_name:
            raise RainfallQualityError('서울 강우 관측소·행 형식 오류')
        try:
            label = datetime.strptime(row['시간'], '%Y-%m-%d %H:%M').replace(tzinfo=KST)
            if label.strftime('%Y-%m-%d %H:%M') != row['시간']:
                raise ValueError()
            depth = Decimal(row['10분우량'])
        except (ValueError, InvalidOperation):
            raise RainfallQualityError('서울 강우 시각·수치 형식 오류') from None
        result.append(SeoulRainRecord(label, depth, line))
    if not result:
        raise RainfallQualityError('서울 강우 관측 누락')
    return result


def annual_audit(rows: list[SeoulRainRecord], year: int) -> dict:
    start = datetime(year, 1, 1, tzinfo=KST)
    end = datetime(year + 1, 1, 1, tzinfo=KST)
    counts = Counter(row.label for row in rows)
    expected = int((end - start) / STEP)
    present = sum(start <= label < end and label.minute % 10 == 9 for label in counts)
    return {
        'year': year, 'rowCount': len(rows), 'expectedTenMinuteIntervals': expected,
        'missingAlignedIntervals': expected - present,
        'duplicateTimestampRows': sum(count - 1 for count in counts.values()),
        'irregularTimestampRows': sum(row.label.minute % 10 != 9 for row in rows),
        'outsideYearRows': sum(not start <= row.label < end for row in rows),
        'invalidDepthRows': sum(not row.depth.is_finite() or row.depth < 0 for row in rows),
        'firstLabelKst': min(counts).isoformat(), 'lastLabelKst': max(counts).isoformat(),
    }


def normalize_window(rows: list[SeoulRainRecord], station_id: str, source_hash: str,
                     start: datetime, end: datetime) -> tuple[list[RainInterval], Decimal]:
    if any(t.utcoffset() is None or t.minute % 10 or t.second or t.microsecond for t in (start, end)):
        raise RainfallQualityError('서울 강우 요청 구간 경계 오류')
    intervals = []
    for row in rows:
        if not start <= row.label < end:
            continue
        if row.label.minute % 10 != 9:
            raise RainfallQualityError('서울 강우 불규칙 시각')
        # 끝 분 표기를 다음 구간 시작 시각으로 이동해 반열린 구간 구성.
        right = row.label + timedelta(minutes=1)
        intervals.append(RainInterval(station_id, right - STEP, right, row.depth,
                                     'BASIC_CHECKED_UNCORRECTED', f'{source_hash}:{row.line}'))
    total = require_complete(intervals, start, end, 600, QUALITY)
    return intervals, total


def aggregate_complete_minutes(rows: list[RainInterval]) -> tuple[list[RainInterval], dict]:
    if not rows:
        raise RainfallQualityError('분 관측 누락')
    require_complete(rows, rows[0].start, rows[-1].end, 60, frozenset({'BASIC_CHECKED'}))
    start = rows[0].start.astimezone(KST)
    if start.second or start.microsecond:
        raise RainfallQualityError('분 관측 경계 오류')
    left = start + timedelta(minutes=(-start.minute) % 10)
    right = rows[-1].end.astimezone(KST)
    right -= timedelta(minutes=right.minute % 10)
    if left >= right:
        raise RainfallQualityError('완전한 10분 관측 구간 없음')
    selected = [row for row in rows if left <= row.start and row.end <= right]
    result = []
    for offset in range(0, len(selected), 10):
        group = selected[offset:offset + 10]
        depth = require_complete(group, group[0].start, group[0].start + STEP, 60,
                                 frozenset({'BASIC_CHECKED'}))
        result.append(RainInterval(group[0].station_id, group[0].start, group[-1].end, depth,
                                   'BASIC_CHECKED', f'{group[0].source_record_id}..{group[-1].source_record_id}'))
    discarded = [row for row in rows if row.start < left or row.end > right]
    return result, {
        'startKst': left.isoformat(), 'endKst': right.isoformat(),
        'excludedLeadingMinutes': int((left - rows[0].start).total_seconds() / 60),
        'excludedTrailingMinutes': int((rows[-1].end - right).total_seconds() / 60),
        'excludedDepthMm': float(sum((row.depth_mm for row in discarded), Decimal(0))),
    }
