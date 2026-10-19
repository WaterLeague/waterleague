"""등록 재해의 7일 선행 공개 관측 원문과 초기화 입력 보존."""
import gzip
import hashlib
import json
import os
import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from local_config import ROOT, load
from prepare_disaster_evaporation import saved

sys.path.insert(0, str(ROOT/'simulation'))
from waterleague_sim.ingestion import antecedent, evaporation, live, hourly_rainfall
from waterleague_sim.ingestion.rainfall import RainfallQualityError
from waterleague_sim.engine.initialization import MINUTES
from waterleague_sim.model_catalog import read_catalog

def aws(station, start, end, key):
    return saved(live.ENDPOINT, {'tm1':start.astimezone(live.KST).strftime('%Y%m%d%H%M'),
        'tm2':end.astimezone(live.KST).strftime('%Y%m%d%H%M'), 'stn':station,'disp':'0','help':'1'},key)


def resilient_aws(station, start, end, key):
    try:
        return aws(station,start,end,key)
    except ValueError as error:
        if str(error).startswith(('기상청 HTTP 504:', '기상청 원본 수집 실패:')):
            raise live.LiveSourceError('KMA_UNAVAILABLE') from None
        raise

DIRECTORY = ROOT/'data/derived/antecedent'


def encode(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)+'\n').encode()


def save(name, value):
    raw = gzip.compress(encode(value), mtime=0)
    path = DIRECTORY/name
    if path.exists() and path.read_bytes() != raw:
        raise ValueError('기존 선행 입력 변경 거부')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return {'file': name, 'sha256': hashlib.sha256(raw).hexdigest()}


def prepare(event):
    key = os.environ.get('KMA_API_KEY', '')
    end = datetime.strptime(event['startKst'], '%Y%m%d%H%M').replace(tzinfo=live.KST)
    start = end-timedelta(minutes=MINUTES)
    pet_file = f"{event['id']}-pet-v1.json.gz"
    if (DIRECTORY/pet_file).exists():
        pet = json.loads(gzip.decompress((DIRECTORY/pet_file).read_bytes()))
    else:
        pet, _ = antecedent.weather(start, end, key, saved)
    pet_entry = save(pet_file, pet)
    stations = sorted({m['stationId'] for m in event['models']})
    def station(station_id):
        name = f"{event['id']}-{station_id}-rain-v1.json.gz"
        path = DIRECTORY/name
        if path.exists():
            rain = json.loads(gzip.decompress(path.read_bytes()))
        else:
            try:
                forcing, sources = live.observed_forcing(station_id, start, end, key, chunk_hours=6, antecedent_quality=True)
                rain = {k: forcing[k] for k in ('start','end','stationId','intervalSeconds','sourceHashes','evidence','qualityWarnings','qualityPolicy','aggregatedRainIntervals')}
                rain['depthsMm'] = [v['depthMm'] for v in forcing['observations']]
                rain['depthMethods'] = [v['method'] for v in forcing['observations']]
                rain['reconstructedMinutes'] = sum(m.startswith('OBSERVED_ZERO_') for m in rain['depthMethods'])
                rain['sourceRequests'] = [s for _, s in sources]
            except RainfallQualityError:
                if station_id != '108': raise
                rain, _ = hourly_rainfall.observed(station_id,start,end,key,saved)
        entry = save(name, rain)
        print(event['id'], station_id, len(rain['depthsMm']), '분 선행 강우 확보', flush=True)
        return {'eventId': event['id'], 'stationId': station_id, 'rainfall': entry, 'evaporation': pet_entry,
            'modelHashes': [m['modelHash'] for m in event['models'] if m['stationId'] == station_id]}
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [(station_id,pool.submit(station,station_id)) for station_id in stations]
        results, errors = [], []
        for station_id, future in futures:
            try: results.append(future.result())
            except Exception as error:
                code = str(error)
                code = code if code.startswith(('AWS_','KMA_')) and len(code)<80 else 'PUBLIC_SOURCE_UNAVAILABLE'
                print(event['id'],station_id,'미확보',code, str(error).replace(key,'[비밀값 제거]')[:160] if isinstance(error,ValueError) else type(error).__name__,flush=True)
                errors.append({'eventId':event['id'],'stationId':station_id,'code':code})
        return results, errors


def archived_forcing(station, start, end, key, **kwargs):
    # 원문 전체를 검증하고 필요한 창만 정규화한다. 결측은 정규화 규칙으로만 판정한다.
    lower = start-timedelta(minutes=61)
    rows, sources = {}, []
    for path in sorted((ROOT/'data/manifests').glob('kma-disaster-pet-*.json')):
        meta=json.loads(path.read_text())
        parameters=meta['parameters']
        if meta['endpoint'] != live.ENDPOINT or parameters.get('stn') != station: continue
        first,last=[datetime.strptime(parameters[k],'%Y%m%d%H%M').replace(tzinfo=live.KST) for k in ('tm1','tm2')]
        if last < lower or first > end: continue
        raw_path=ROOT/'data/raw'/(path.stem+'.txt')
        raw=raw_path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=meta['sha256']: raise ValueError('보관 선행 원문 해시 오류')
        for at,value in live.parse(raw,station,first,last).items():
            if not lower <= at <= end: continue
            if at in rows and rows[at]!=value: raise RainfallQualityError('AWS_OVERLAPPING_RESPONSE_CHANGED')
            rows[at]=value
        sources.append((raw,meta|{'rawFile':str(raw_path.relative_to(ROOT)),'purpose':'HISTORICAL_SIMULATION_INPUT'}))
    warnings,intervals=[],[]
    observations=live.normalized(rows,start,end,rolling_warnings=warnings,interval_averages=intervals)
    return {'start':start.isoformat(),'end':end.isoformat(),'stationId':station,'intervalSeconds':60,
        'sourceHashes':[m['sha256'] for _,m in sources], 'evidence':'OBSERVED_AWS_DERIVED_INTERVAL_DEPTH',
        'qualityPolicy':'ANTECEDENT_DAILY_COUNTER_PRIMARY_ROLLING_CHECK_RECORDED','qualityWarnings':warnings,
        'aggregatedRainIntervals':intervals,'observations':observations}, sources


def main():
    global DIRECTORY, saved
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,default=DIRECTORY)
    parser.add_argument('--archived-only',action='store_true')
    args=parser.parse_args()
    DIRECTORY=args.output
    load()
    if not args.archived_only and not os.environ.get('KMA_API_KEY'):
        raise SystemExit('원문 수집용 기존 KMA_API_KEY 필요; 보관 원문 재생은 --archived-only 사용')
    if args.archived_only:
        network_saved=saved
        def cached(endpoint,parameters,key):
            payload=(json.dumps({'endpoint':endpoint,'parameters':parameters},ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode()
            stem='kma-disaster-pet-'+hashlib.sha256(payload).hexdigest()[:24]
            if not (ROOT/'data/raw'/(stem+'.txt')).exists(): raise ValueError('보관 원문 미확보: '+stem)
            return network_saved(endpoint,parameters,key)
        saved=cached
    evaporation.fetch = saved
    evaporation.fetch_range = aws
    live.fetch_range = resilient_aws
    if args.archived_only:
        live.observed_forcing = archived_forcing
    events = json.loads((ROOT/'backend/src/main/resources/disasters/seoul-events-v1.json').read_text())['events']
    entries, failures = [], []
    for event in events:
        ready, errors = prepare(event)
        entries.extend(ready); failures.extend(errors)
    if failures:
        (ROOT/'tmp/antecedent-progress.json').write_bytes(encode({'ready':len(entries),'failures':failures}))
        raise SystemExit('일부 선행 입력 미확보; 확보 원문을 보존한 재시도 필요')
    implementations = {}
    for module in ('ingestion/live.py','ingestion/antecedent.py','ingestion/daily_evaporation.py','ingestion/hourly_rainfall.py','ingestion/evaporation.py','engine/evapotranspiration.py'):
        body=(ROOT/'simulation/waterleague_sim'/module).read_bytes()
        sha=hashlib.sha256(body).hexdigest()
        target=DIRECTORY/'implementations'/(sha+'.py');target.parent.mkdir(exist_ok=True);target.write_bytes(body)
        implementations[module]=sha
    value = {'schemaVersion': 1, 'warmupMinutes': MINUTES, 'implementationHashes': implementations,
        'generatorSha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'entries': entries}
    (DIRECTORY/'generator.py').write_bytes(Path(__file__).read_bytes())
    path = DIRECTORY/'catalog-v1.json'
    data = encode(value)
    if path.exists() and path.read_bytes() != data:
        raise ValueError('기존 선행 목록 변경 거부')
    path.write_bytes(data)
    print('catalog', hashlib.sha256(data).hexdigest(), flush=True)


if __name__ == '__main__':
    main()
