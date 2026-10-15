"""정규화된 관측 강우의 구간·품질·누락 검증."""
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal


class RainfallQualityError(ValueError):
    pass


@dataclass(frozen=True)
class RainInterval:
    station_id: str
    start: datetime
    end: datetime
    depth_mm: Decimal | None
    quality: str
    source_record_id: str


def require_complete(intervals: list[RainInterval], start: datetime, end: datetime,
                     interval_seconds: int, approved_quality_codes: frozenset[str]) -> Decimal:
    if start.utcoffset() is None or end.utcoffset() is None or start >= end or interval_seconds <= 0:
        raise RainfallQualityError('검증 기간·시간대·간격 오류')
    if not intervals or not approved_quality_codes:
        raise RainfallQualityError('관측·품질 정책 누락')
    cursor = start
    station = intervals[0].station_id
    record_ids = set()
    total = Decimal('0')
    for row in intervals:
        if row.start.utcoffset() is None or row.end.utcoffset() is None:
            raise RainfallQualityError('관측 시간대 누락')
        if row.start != cursor or row.end - row.start != timedelta(seconds=interval_seconds) or row.end > end:
            raise RainfallQualityError('결측·중복·구간 길이 오류')
        if not station or row.station_id != station or not row.source_record_id or row.source_record_id in record_ids:
            raise RainfallQualityError('관측소·원본 레코드 불일치')
        if row.quality not in approved_quality_codes or row.depth_mm is None:
            raise RainfallQualityError('미승인 품질·결측 관측')
        if not row.depth_mm.is_finite() or row.depth_mm < 0:
            raise RainfallQualityError('비정상 강우값')
        record_ids.add(row.source_record_id)
        total += row.depth_mm
        cursor = row.end
    if cursor != end:
        raise RainfallQualityError('관측기간 미충족')
    return total
