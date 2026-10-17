"""고정 서울 원본과 KMA 분 관측의 동일 시간 구간 비교."""
import hashlib
import json
import sys
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from xml.etree import ElementTree
from zipfile import ZipFile

from pyproj import Geod

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'simulation'))
from waterleague_sim.ingestion.kma import normalize as normalize_kma
from waterleague_sim.ingestion.seoul import KST, aggregate_complete_minutes, annual_audit, normalize_window, parse

STATIONS = [('901', '성동구청', '성동구청2024.csv'), ('902', '뚝섬P', '뚝섬펌프장2024.csv')]
WINDOWS = [('202406220001', '202406222359'), ('202407020001', '202407022359'),
           ('202407180500', '202407182359')]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def checked_raw(filename, manifest_name=None):
    manifest = json.loads((ROOT / 'data/manifests' / (manifest_name or filename + '.json')).read_text())
    path = ROOT / 'data/raw' / filename
    if digest(path.read_bytes()) != manifest['sha256']:
        raise ValueError('관측 원본 해시 불일치')
    return path, manifest


def locations(path):
    ns = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    with ZipFile(path) as archive:
        if sum(item.file_size for item in archive.infolist()) > 2_000_000:
            raise ValueError('위치 원본 압축 해제 크기 초과')
        strings = [''.join(node.itertext()) for node in
                   ElementTree.fromstring(archive.read('xl/sharedStrings.xml')).findall('m:si', ns)]
        sheet = ElementTree.fromstring(archive.read('xl/worksheets/sheet1.xml'))
        result = {}
        for row in sheet.findall('m:sheetData/m:row', ns)[1:]:
            values = {}
            for cell in row.findall('m:c', ns):
                value = cell.find('m:v', ns)
                if value is not None:
                    column = ''.join(c for c in cell.attrib['r'] if c.isalpha())
                    values[column] = strings[int(value.text)] if cell.attrib.get('t') == 's' else value.text
            code = values['D']
            if code in result:
                raise ValueError('중복 강우량계 코드')
            longitude, latitude = float(values['F']), float(values['G'])
            if not 126 < longitude < 128 or not 37 < latitude < 38:
                raise ValueError('서울 관측소 좌표 오류')
            _, _, distance = Geod(ellps='WGS84').inv(127.054, 37.54425, longitude, latitude)
            result[code] = {'stationId': code, 'name': values['B'], 'address': values['C'],
                            'longitude': longitude, 'latitude': latitude, 'distanceToModelCenterKm': round(distance / 1000, 3),
                            'metadataDate': '2026-09-15', 'historical2024LocationStatus': 'UNVERIFIED'}
        return result


def main():
    raw, raw_manifest = checked_raw('seoul-rain-2021-2024.zip')
    location_path, location_manifest = checked_raw('seoul-rain-stations-20260915.xlsx')
    coordinates = locations(location_path)
    report = {'schemaVersion': 1, 'purpose': '인접 관측소 강우의 동일 시간 구간 비교', 'officialValidation': False,
              'license': '공공누리 1유형 · 서울특별시 치수안전과 출처 표시',
              'sources': [raw_manifest, location_manifest], 'codeHashes': {
                  str(path.relative_to(ROOT)): digest(path.read_bytes()) for path in [Path(__file__),
                      ROOT / 'simulation/waterleague_sim/ingestion/seoul.py',
                      ROOT / 'simulation/waterleague_sim/ingestion/kma.py',
                      ROOT / 'simulation/waterleague_sim/ingestion/rainfall.py']},
              'intervalSeconds': 600, 'quality': 'BASIC_CHECKED_UNCORRECTED',
              'timeConventionSource': 'https://data.seoul.go.kr/bsp/wgs/dataView/data300View/1115.do',
              'limitations': ['보정되지 않은 서울시 원시 계측 자료; 자체 완전성 검사만 수행',
                             '현재 좌표와 과거 관측소명의 연결; 2024년 위치 이력 미검증',
                             '10분 누적 관측 보존, 분 관측 생성·결측 0 보간 없음',
                             '관측소 차이는 현장 강우 오차·보정계수·유출 검증이 아님'], 'stations': []}
    kma = {}
    for begin, end in WINDOWS:
        stem = f'kma-421-{begin}-{end}'
        path, manifest = checked_raw(stem + '.txt', stem + '.json')
        intervals, _ = normalize_kma(path.read_text())
        if any(row.station_id != '421' for row in intervals):
            raise ValueError('KMA 비교 관측소 불일치')
        combined, selection = aggregate_complete_minutes(intervals)
        kma[begin[:8]] = (combined, selection, manifest['sha256'])
    with ZipFile(raw) as archive:
        members = {}
        for item in archive.infolist():
            try:
                name = item.filename.encode('cp437').decode('cp949')
            except UnicodeError:
                name = item.filename
            if name in members:
                raise ValueError('중복 압축 파일명')
            members[name] = item
        for code, name, filename in STATIONS:
            if coordinates[code]['name'] != name or members[filename].file_size > 3_000_000:
                raise ValueError('관측소 연결·원본 크기 오류')
            data = archive.read(members[filename])
            source_hash = digest(data)
            records = parse(data.decode('cp949'), name)
            station = {**coordinates[code], 'member': filename, 'memberSha256': source_hash,
                       'annualAudit': annual_audit(records, 2024), 'windows': []}
            for date, (combined, selection, kma_hash) in kma.items():
                start = datetime.strptime(date, '%Y%m%d').replace(tzinfo=KST)
                end = start + timedelta(days=1)
                intervals, total = normalize_window(records, code, source_hash, start, end)
                aligned = [row for row in intervals if combined[0].start <= row.start and row.end <= combined[-1].end]
                if len(aligned) != len(combined) or any((a.start, a.end) != (b.start, b.end) for a, b in zip(aligned, combined)):
                    raise ValueError('서울·KMA 비교 구간 불일치')
                seoul_total = sum((row.depth_mm for row in aligned), Decimal(0))
                kma_total = sum((row.depth_mm for row in combined), Decimal(0))
                station['windows'].append({'startKst': start.isoformat(), 'endKst': end.isoformat(),
                    'count': len(intervals), 'totalDepthMm': float(total),
                    'depthsMm': [float(row.depth_mm) for row in intervals],
                    'comparison': {**selection, 'count': len(aligned), 'kmaStationId': '421', 'kmaSourceSha256': kma_hash,
                                   'kmaDepthsMm': [float(row.depth_mm) for row in combined],
                                   'seoulTotalMm': float(seoul_total), 'kmaTotalMm': float(kma_total),
                                   'seoulMinusKmaMm': float(seoul_total - kma_total)}})
            report['stations'].append(station)
    destination = ROOT / 'data/derived/seoul-rainfall-audit.json'
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    for station in report['stations']:
        print(station['name'], station['distanceToModelCenterKm'], 'km', station['annualAudit'])
        for window in station['windows']:
            comparison = window['comparison']
            print(window['startKst'][:10], window['count'], '구간', window['totalDepthMm'], 'mm',
                  '동일 구간 서울/KMA', comparison['seoulTotalMm'], comparison['kmaTotalMm'], 'mm')


if __name__ == '__main__':
    main()
