"""등록된 재해 강우와 불변 증발산 입력의 해시·시간 연결 검사."""
import json
import re
from datetime import datetime
from pathlib import Path

from .engine.continuous import ROOT, digest
from .ingestion.evaporation import METHOD
from .ingestion.daily_evaporation import METHOD as DAILY_METHOD


def load(model_hash, observed, directory):
    root = ROOT/'data/derived/evaporation'
    catalog = (root/'disaster-catalog-v1.json').read_bytes()
    entries = [e for e in json.loads(catalog)['entries'] if model_hash in e['modelHashes']]
    if len(entries) != 1:
        raise ValueError('HISTORICAL_PET_BINDING_INVALID')
    entry = entries[0]
    if (not re.fullmatch(r'seoul-\d{8}-fao56-v1.json', entry['file'])
            or entry['eventId'] != observed['disasterEvent']['id']):
        raise ValueError('HISTORICAL_PET_BINDING_INVALID')
    raw = (root/entry['file']).read_bytes()
    value = json.loads(raw)
    rain = observed['rainfall']
    if (digest(raw) != entry['sha256'] or value['eventId'] != entry['eventId'] or value['method'] not in (METHOD, DAILY_METHOD)
            or any(datetime.fromisoformat(value[k]) != datetime.fromisoformat(rain[k]) for k in ('start', 'end'))
            or len(value['ratesMmDay']) != len(rain['depthsMm'])):
        raise ValueError('HISTORICAL_PET_INPUT_INVALID')
    directory.mkdir(parents=True, exist_ok=True)
    (directory/'evaporation-catalog.json').write_bytes(catalog)
    (directory/'evaporation.json').write_bytes(raw)
    for source in value['sourceRequests']:
        if not re.fullmatch(r'data/raw/kma-disaster-pet-[a-f0-9]{24}.txt', source['rawFile']):
            raise ValueError('HISTORICAL_PET_SOURCE_INVALID')
        body = (ROOT/source['rawFile']).read_bytes()
        if digest(body) != source['sha256']:
            raise ValueError('HISTORICAL_PET_SOURCE_INVALID')
        (directory/('s'+source['sha256']+'.txt')).write_bytes(body)
    implementations = {'daily_evaporation.py': 'ingestion/daily_evaporation.py'} if value['method'] == DAILY_METHOD else {
        'evaporation.py': 'ingestion/evaporation.py', 'evapotranspiration.py': 'engine/evapotranspiration.py'}
    for name, relative in implementations.items():
        body = (Path(__file__).parent/relative).read_bytes()
        expected = value['implementationHashes'][name]
        if not re.fullmatch(r'[a-f0-9]{64}', expected):
            raise ValueError('HISTORICAL_PET_IMPLEMENTATION_CHANGED')
        if digest(body) != expected:
            # 이미 산정된 증발산의 생성 코드는 실행 시점 코드와 별도로 보존한다.
            archived = root/'implementations'/(expected+'.py')
            if archived.is_symlink() or not archived.is_file():
                raise ValueError('HISTORICAL_PET_IMPLEMENTATION_CHANGED')
            body = archived.read_bytes()
        if digest(body) != expected:
            raise ValueError('HISTORICAL_PET_IMPLEMENTATION_CHANGED')
        (directory/name).write_bytes(body)
    return value
