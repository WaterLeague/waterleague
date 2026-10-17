"""선별 재해의 관측 증발산 입력 보관. 게임 실행 중 과거 기상 API 호출 없음."""
import hashlib
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from local_config import ROOT, load
from fetch_seoul_regional_rainfall import fetch as archive

sys.path.insert(0, str(ROOT/'simulation'))
from waterleague_sim.ingestion import evaporation
from waterleague_sim.ingestion.live import ENDPOINT
from waterleague_sim.ingestion.daily_evaporation import observed_daily


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n').encode()


def saved(endpoint, parameters, key):
    suffix = hashlib.sha256(encoded({'endpoint': endpoint, 'parameters': parameters})).hexdigest()[:24]
    stem = 'kma-disaster-pet-'+suffix
    raw = archive(stem, endpoint, parameters, key)
    meta = json.loads((ROOT/'data/manifests'/f'{stem}.json').read_text())
    return raw, meta | {'rawFile': f'data/raw/{stem}.txt', 'purpose': 'HISTORICAL_SIMULATION_INPUT'}


def aws(station, start, end, key):
    return saved(ENDPOINT, {'tm1': start.astimezone(evaporation.KST).strftime('%Y%m%d%H%M'),
                            'tm2': end.astimezone(evaporation.KST).strftime('%Y%m%d%H%M'),
                            'stn': station, 'disp': '0', 'help': '1'}, key)


def prepare(event):
    start, end = [datetime.strptime(event[k], '%Y%m%d%H%M').replace(tzinfo=evaporation.KST)
                  for k in ('startKst', 'endKst')]
    try:
        value, _ = evaporation.observed_evaporation(start, end, os.environ['KMA_API_KEY'])
    except evaporation.LiveSourceError as error:
        if str(error) != 'KMA_PET_HOURLY_WEATHER_MISSING':
            raise
        value, _ = observed_daily(start, end, os.environ['KMA_API_KEY'], saved)
        value['temporalResolutionReason'] = str(error)
    value.update({'eventId': event['id'], 'start': start.isoformat(), 'end': end.isoformat()})
    data = encoded(value)
    path = ROOT/'data/derived/evaporation'/f"{event['id']}-fao56-v1.json"
    if path.exists() and path.read_bytes() != data:
        raise ValueError('기존 재해 증발산 입력 덮어쓰기 거부')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    print(event['id'], '관측 증발산', len(value['ratesMmDay']), '분 확보', flush=True)
    return {'eventId': event['id'], 'file': path.name, 'sha256': hashlib.sha256(data).hexdigest(),
            'modelHashes': [m['modelHash'] for m in event['models']]}


def main():
    load()
    if not os.environ.get('KMA_API_KEY'):
        raise SystemExit('기존 .env.local KMA_API_KEY 필요')
    evaporation.fetch = saved
    evaporation.fetch_range = aws
    events = json.loads((ROOT/'backend/src/main/resources/disasters/seoul-events-v1.json').read_text())['events']
    with ThreadPoolExecutor(max_workers=3) as pool:
        entries = list(pool.map(prepare, events))
    (ROOT/'data/derived/evaporation/disaster-catalog-v1.json').write_bytes(encoded({'schemaVersion': 1, 'entries': entries}))


if __name__ == '__main__':
    main()
