"""검증된 AWS 관측 창을 별도 모델로 등록. 기존 모델 원문 보존."""
from pathlib import Path
from datetime import datetime, timezone, timedelta
import sys
import json
import hashlib
import copy
from decimal import Decimal
from pyproj import Geod
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'simulation'))
from waterleague_sim.ingestion.kma import normalize


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')


def statistics(rows):
    wet = [i for i, row in enumerate(rows) if row.depth_mm > 0]
    if not wet:
        raise ValueError('무강우 창 등록 불가')
    return {'peak15MinuteMm': float(max(sum((r.depth_mm for r in rows[i:i+15]), Decimal(0)) for i in range(len(rows)-14))),
            'peak60MinuteMm': float(max(sum((r.depth_mm for r in rows[i:i+60]), Decimal(0)) for i in range(len(rows)-59))),
            'firstWetIntervalStart': rows[wet[0]].start.isoformat(),
            'lastWetIntervalEnd': rows[wet[-1]].end.isoformat(),
            'observedDryLeadMinutes': wet[0], 'observedDryTailMinutes': len(rows)-1-wet[-1]}


def main():
    source = ROOT/'data/models/seongsu-lab.json'
    base = json.loads(source.read_text())
    old_hash = digest(source.read_bytes())
    metadata = json.loads((ROOT/'data/derived/kma-station-421.json').read_text())
    _, _, distance = Geod(ellps='WGS84').inv(127.054, 37.54425, metadata['longitude'], metadata['latitude'])
    entries = [{'id': base['id'], 'file': source.name, 'sha256': old_hash}]
    events = []
    for start, end in [('202406220001', '202406222359'), ('202407020001', '202407022359'), ('202407180500', '202407182359')]:
        raw = ROOT/f'data/raw/kma-421-{start}-{end}.txt'
        manifest_path = ROOT/f'data/manifests/{raw.stem}.json'
        manifest = json.loads(manifest_path.read_text())
        data = raw.read_bytes()
        if manifest['sha256'] != digest(data):
            raise ValueError('원본 해시 불일치')
        rows, total = normalize(data.decode())
        if any(r.station_id != '421' for r in rows):
            raise ValueError('관측소 불일치')
        stamp = lambda value: datetime.strptime(value, '%Y%m%d%H%M').replace(tzinfo=timezone(timedelta(hours=9))).astimezone(timezone.utc)
        if rows[0].start != stamp(start) or rows[-1].end != stamp(end):
            raise ValueError('요청 창과 실제 관측 창 불일치')
        event = copy.deepcopy(base['rainfall'])
        event.update({'id': raw.stem, 'stationId': '421', 'stationName': '성동',
                      'stationDistanceKm': round(distance/1000, 3),
                      'stationDistanceEvidence': '공식 현재 지점 상세 좌표에서 구역 중심까지 WGS84 지오데식 거리; 2024년 위치 이력·현장 대표성 미검증',
                      'stationMetadata': metadata, 'start': rows[0].start.isoformat(), 'end': rows[-1].end.isoformat(),
                      'depthsMm': [float(r.depth_mm) for r in rows], 'totalDepthMm': float(total),
                      'sourceHash': digest(data), 'sourceManifest': manifest_path.name,
                      'windowStatistics': statistics(rows), 'windowType': 'OBSERVED_WINDOW_NOT_COMPLETE_STORM',
                      'limitations': [
                          '관측 창의 일부만 사용; 완전한 강우 사상·재현기간·설계호우 아님',
                          '현장 강우 대표성·관측소 2024년 위치 이력 미검증',
                          '선행 강우·초기 토양수분 보정 없음',
                          '별도 기상청 품질 플래그 미제공; 자체 일관성 검사만 통과',
                          '관측기간 밖 강우·무강우 보간 없음; 최종 잔여저류를 평가체적에 포함']})
        event_path = ROOT/f'data/derived/rainfall/{raw.stem}.json'
        write(event_path, event)
        model = copy.deepcopy(base)
        model.update({'id': f'seongsu-421-{start[:8]}', 'title': f'성수 탐색 · 성동 {start[:4]}.{start[4:6]}.{start[6:8]}',
                      'rainfall': event, 'rainfallSource': f'기상청 성동 421 관측소 · {start[:8]}',
                      'assumptions': [s for s in base['assumptions'] if not s.startswith('2024-07-18')] + [
                          '고정 관측 창만 계산하며 후속 무강우를 임의 생성하지 않음',
                          f'관측된 후행 무강우 {event["windowStatistics"]["observedDryTailMinutes"]}분; 장기 배수·저류 회복 효과 미검증']})
        path = ROOT/f'data/models/{model["id"]}.json'
        write(path, model)
        entries.append({'id': model['id'], 'file': path.name, 'sha256': digest(path.read_bytes())})
        events.append({'id': event['id'], 'totalDepthMm': event['totalDepthMm'], **event['windowStatistics']})
    write(ROOT/'data/models/catalog.json', {'schemaVersion': 1, 'defaultModelHash': old_hash, 'models': entries})
    for entry in entries:
        (ROOT/'backend/src/main/resources/models'/entry['file']).write_bytes((ROOT/'data/models'/entry['file']).read_bytes())
    (ROOT/'backend/src/main/resources/models/catalog.json').write_bytes((ROOT/'data/models/catalog.json').read_bytes())
    old_rows, old_total = normalize((ROOT/'data/raw/kma-108-202407180500-202407182359.txt').read_text())
    write(ROOT/'data/derived/rainfall-comparison.json', {'purpose': '강우 창·관측소 차이의 탐색 비교', 'officialValidation': False,
          'sameWindowComparison': {'start': old_rows[0].start.isoformat(), 'end': old_rows[-1].end.isoformat(),
          'seoul108': {'totalDepthMm': float(old_total), **statistics(old_rows)}, 'seongdong421': events[-1],
          'totalDepthDifferenceMm421Minus108': float(total-old_total),
          'limitation': '두 지점 차이의 관측 사례이며 성수 현장 오차 추정·공간 보정 계수 아님'}, 'windows': events})
    assert digest(source.read_bytes()) == old_hash
    for event in events:
        print(event['id'], event['totalDepthMm'], 'mm', '관측 후행 무강우', event['observedDryTailMinutes'], '분')


if __name__ == '__main__':
    main()
