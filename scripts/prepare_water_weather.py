"""보관된 공개 기상에서 수면 표현용 풍속을 추출한다."""
import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
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
