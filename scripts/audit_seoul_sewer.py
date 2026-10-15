"""성동구 수위 원시 행 추출·품질 점검. 수위 단위·유량 변환 추정 금지."""
import csv
import hashlib
import io
import json
from collections import Counter
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
DAYS = {'2024-06-22', '2024-07-02', '2024-07-18'}
MONTHS = {'202406', '202407'}
HEADER = ['?고유번호', '구분코드', '구분명', '측정일자', '측정수위', '통신상태']


def summary(rows, day):
    timestamps = Counter()
    statuses = Counter()
    values = []
    malformed_time = invalid_depth = negative = irregular = 0
    start = datetime.fromisoformat(day)
    for row in rows:
        statuses[row[5]] += 1
        try:
            time = datetime.strptime(row[3], '%Y-%m-%d %H:%M:%S.%f')
            if time.date() != start.date():
                raise ValueError()
            timestamps[time] += 1
            irregular += bool(time.second or time.microsecond)
        except ValueError:
            malformed_time += 1
        try:
            value = Decimal(row[4])
            if not value.is_finite():
                raise ValueError()
            values.append(value)
            negative += value < 0
        except (ValueError, InvalidOperation):
            invalid_depth += 1
    missing = [minute for minute in range(1440) if start + timedelta(minutes=minute) not in timestamps]
    longest = current = 0
    previous = -2
    for minute in missing:
        current = current + 1 if minute == previous + 1 else 1
        longest = max(longest, current)
        previous = minute
    return {'dateLabel': day, 'rowCount': len(rows), 'uniqueTimestamps': len(timestamps),
            'duplicateTimestampRows': sum(count - 1 for count in timestamps.values()),
            'nominalOneMinuteGridSize': 1440, 'missingOnOneMinuteGrid': len(missing),
            'longestMissingMinutes': longest, 'irregularTimestampRows': irregular,
            'malformedTimestampRows': malformed_time, 'invalidValueRows': invalid_depth,
            'negativeValueRows': negative, 'communicationStatusCounts': dict(sorted(statuses.items())),
            'distinctFiniteValues': len(set(values)), 'constantFiniteValues': bool(values) and len(set(values)) == 1,
            'minimumRawValue': str(min(values)) if values else None,
            'maximumRawValue': str(max(values)) if values else None,
            'firstLabel': min(timestamps).isoformat() if timestamps else None,
            'lastLabel': max(timestamps).isoformat() if timestamps else None}


def main():
    path = ROOT / 'data/raw/seoul-sewer-2024.zip'
    manifest = json.loads((ROOT / 'data/manifests/seoul-sewer-2024.zip.json').read_text())
    with path.open('rb') as source:
        if hashlib.file_digest(source, 'sha256').hexdigest() != manifest['sha256']:
            raise ValueError('하수관로 원본 해시 불일치')
    selections = {}
    station_ids = set()
    report = {'schemaVersion': 1, 'purpose': '공개 성동구 수위 자료의 확보·품질 조사',
              'calibrationEligible': False, 'source': manifest, 'measurementUnit': 'UNVERIFIED',
              'verticalDatum': 'NOT_PROVIDED', 'locationInHistoricalCsv': 'NOT_PROVIDED',
              'timeZone': 'UNVERIFIED_SOURCE_HAS_NO_OFFSET',
              'codeSha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'limitations': ['위치·수위 단위·기준면·관측 단면·실제 유역 연결 미검증',
                             '통신양호는 계측값의 검보정 완료를 의미하지 않음',
                             '정시 1분 격자는 관측 패턴에 대한 점검 기준이며 공급자의 품질 승인 기준이 아님',
                             '수위를 유량으로 변환하거나 결측을 0으로 대체하지 않음'], 'members': [], 'stations': []}
    with ZipFile(path) as archive:
        for member in archive.infolist():
            try:
                name = member.filename.encode('cp437').decode('cp949')
            except UnicodeError:
                name = member.filename
            if not any(name == f'하수관로_수위_현황_{month}.csv' for month in MONTHS):
                continue
            if member.file_size > 800_000_000:
                raise ValueError('월별 원본 크기 초과')
            hasher = hashlib.sha256()
            count = byte_count = selected = 0
            with archive.open(member) as source:
                for line in source:
                    hasher.update(line)
                    count += 1
                    byte_count += len(line)
                    if len(line) > 10000 or byte_count > member.file_size:
                        raise ValueError('월별 원본 행·크기 오류')
                    if count == 1:
                        if next(csv.reader([line.decode('cp949')])) != HEADER:
                            raise ValueError('수위 원본 헤더 불일치')
                        continue
                    # 원본을 전부 읽어 CRC·해시를 검사하되 대상 구만 행 파싱.
                    if b',04,' not in line:
                        continue
                    row = next(csv.reader([line.decode('cp949')]))
                    if len(row) != 6 or row[1:3] != ['04', '성동'] or not row[0].startswith('04-'):
                        raise ValueError('성동구 원본 행 형식 오류')
                    station_ids.add(row[0])
                    day = row[3][:10]
                    if day in DAYS:
                        selections.setdefault((row[0], day), []).append(row)
                        selected += 1
            if byte_count != member.file_size:
                raise ValueError('월별 원본 누락')
            report['members'].append({'filename': name, 'sha256': hasher.hexdigest(), 'bytes': byte_count,
                                       'physicalDataLines': count - 1, 'selectedRows': selected})
            print(name, count - 1, '원본 행', selected, '선택 행', flush=True)
    if len(report['members']) != 2 or not selections:
        raise ValueError('대상 월·성동 관측 누락')
    out = io.StringIO(newline='')
    writer = csv.writer(out, lineterminator='\n')
    writer.writerow(HEADER)
    for station in sorted(station_ids):
        windows = []
        for day in sorted(DAYS):
            rows = selections.get((station, day), [])
            windows.append(summary(rows, day))
            writer.writerows(rows)
        report['stations'].append({'stationId': station, 'windows': windows})
    selected_bytes = out.getvalue().encode('utf-8')
    selected_path = ROOT / 'data/raw/seoul-sewer-seongdong-selected.csv'
    if selected_path.exists() and selected_path.read_bytes() != selected_bytes:
        raise ValueError('기존 수위 선택 행과 불일치')
    selected_path.write_bytes(selected_bytes)
    report['selectedCsv'] = {'filename': selected_path.name, 'encoding': 'UTF-8',
                             'sha256': hashlib.sha256(selected_bytes).hexdigest(), 'bytes': len(selected_bytes),
                             'rows': sum(len(rows) for rows in selections.values())}
    destination = ROOT / 'data/derived/seoul-sewer-audit.json'
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    for station in report['stations']:
        print(station['stationId'], [(w['dateLabel'], w['rowCount'], w['missingOnOneMinuteGrid'],
                                     w['communicationStatusCounts']) for w in station['windows']])


if __name__ == '__main__':
    main()
