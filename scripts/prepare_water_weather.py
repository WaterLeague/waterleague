"""보관된 공개 기상에서 수면 표현용 풍향·풍속을 추출한다."""
import hashlib
import json
import math
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def prepare_legacy():
    entries = []
    for event in ["20220808", "20110727", "20100921"]:
        source = ROOT / f"data/derived/evaporation/seoul-{event}-fao56-v1.json"
        raw = source.read_bytes()
        value = json.loads(raw)
        samples = []
        for hour in value.get("hours", []):
            samples.append({"from": hour["appliesFrom"], "until": hour["appliesUntil"],
                            "windSpeedMs": hour["meanWeather"]["windSpeedMs"]})
        for day in value.get("days", []):
            start = date.fromisoformat(day["date"])
            samples.append({"from": f"{start}T00:00:00+09:00",
                            "until": f"{start + timedelta(days=1)}T00:00:00+09:00",
                            "windSpeedMs": day["weather"]["windMs"]})
        entries.append({"eventId": value["eventId"], "stationName": value["station"]["stationName"],
                        "stationId": value["station"]["stationId"], "resolution": "HOUR" if value.get("hours") else "DAY",
                        "sourceFile": source.name, "sourceSha256": hashlib.sha256(raw).hexdigest(), "samples": samples})
    output = ROOT / "frontend/public/data/water-weather-v1.json"
    output.write_text(json.dumps({"version": "ARCHIVED_WATER_WEATHER_V1", "entries": entries}, ensure_ascii=False, indent=2) + "\n")
    print(output.relative_to(ROOT))


# 표시용 풍향은 증발산 평균값 대신 같은 구의 보관 AWS 분 원문에서 읽는다.
def minute_wind(raw, station_id):
    text = raw.decode('utf-8')
    if not (text.startswith('#START7777') and text.strip().endswith('#7777END')
            and '#  WD1' in text and '#  WS1' in text and '360-무풍' in text):
        raise ValueError('풍향·풍속 원문 형식 불일치')
    rows = {}
    for line in text.splitlines():
        if not line.strip() or line.startswith('#'):
            continue
        fields = line.split()
        if len(fields) != 18 or fields[1] != station_id or fields[0] in rows:
            raise ValueError('풍향·풍속 관측소·중복 시각 오류')
        direction, speed = map(float, fields[2:4])
        speed = speed if math.isfinite(speed) and 0 <= speed <= 150 else None
        direction = direction if speed and math.isfinite(direction) and 0 <= direction < 360 else None
        rows[fields[0]] = [speed, direction]
    return rows


def prepare_minute_weather():
    for event in ['20220808', '20110727', '20100921']:
        selection_path = ROOT / f'data/manifests/seoul-{event}-selection-v1.json'
        selection_raw = selection_path.read_bytes()
        selection = json.loads(selection_raw)
        start = datetime.strptime(selection['event']['startKst'], '%Y%m%d%H%M')
        end = datetime.strptime(selection['event']['endKst'], '%Y%m%d%H%M')
        stations = {}
        for item in selection['selections']:
            if item['status'] != 'ACCEPTED':
                raise ValueError('기존 강우 관측소 미확정')
            station_id = item['stationId']
            rain_raw = (ROOT / f'data/derived/rainfall/{item["rainfallId"]}.json').read_bytes()
            if hashlib.sha256(rain_raw).hexdigest() != item['rainfallSha256']:
                raise ValueError('기존 강우 자료 해시 불일치')
            rain = json.loads(rain_raw)
            manifest = json.loads((ROOT / 'data/manifests' / rain['sourceManifest']).read_bytes())
            source_file = rain['sourceManifest'].replace('.json', '.txt')
            raw = (ROOT / 'data/raw' / source_file).read_bytes()
            source_sha = hashlib.sha256(raw).hexdigest()
            if source_sha != manifest['sha256'] or source_sha != rain['sourceHash']:
                raise ValueError('기존 AWS 원문 해시 불일치')
            if station_id in stations:
                if stations[station_id]['sourceSha256'] != source_sha:
                    raise ValueError('동일 관측소의 원문 불일치')
                stations[station_id]['districtIds'].append(item['districtId'])
                continue
            rows = minute_wind(raw, station_id)
            samples = [rows.get((start + timedelta(minutes=i)).strftime('%Y%m%d%H%M'), [None, None])
                       for i in range(int((end - start).total_seconds() // 60))]
            stations[station_id] = {
                'stationId': station_id, 'stationName': rain['stationName'],
                'districtIds': [item['districtId']], 'sourceFile': source_file,
                'sourceSha256': source_sha, 'samples': samples,
            }
        payload = {
            'version': 'ARCHIVED_WATER_WEATHER_V2', 'eventId': f'seoul-{event}',
            'start': start.isoformat() + '+09:00', 'end': end.isoformat() + '+09:00',
            'intervalSeconds': 60, 'fields': ['WS1', 'WD1'],
            'timePolicy': 'COMPLETED_ONE_MINUTE_MEAN_HELD_OVER_NEXT_MINUTE',
            'selectionSha256': hashlib.sha256(selection_raw).hexdigest(),
            'stations': list(stations.values()),
        }
        directory = ROOT / 'frontend/public/data/water-weather-v2'
        directory.mkdir(exist_ok=True)
        path = directory / f'seoul-{event}.json'
        path.write_text(json.dumps(payload, ensure_ascii=False, separators=(',', ':'), allow_nan=False) + '\n')
        missing = sum(speed is None for s in stations.values() for speed, direction in s['samples'])
        print(path.relative_to(ROOT), len(stations), '관측소', missing, '풍속 결측')


if __name__ == "__main__":
    prepare_legacy()
    prepare_minute_weather()
