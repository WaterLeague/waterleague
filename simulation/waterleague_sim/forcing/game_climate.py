"""원형 공간 게임의 과거 관측·증발산·7일 선행 입력 재현 보존."""
import gzip
import io
import json
from pathlib import Path
import re
from datetime import datetime, timedelta

from ..spatial import game_catalog
from .archived_game_weather import read_source, implementation_source, digest


def _weather_sources(value, directory):
    for reference in value['sourceRequests']:
        if not re.fullmatch(r'data/raw/kma-disaster-pet-[a-f0-9]{24}\.txt', reference['rawFile']):
            raise ValueError('HISTORICAL_WEATHER_SOURCE_INVALID')
        body = read_source(reference['rawFile'], reference['sha256'])
        if len(body) != reference['bytes']:
            raise ValueError('HISTORICAL_WEATHER_SOURCE_INVALID')
        (directory / ('s' + reference['sha256'] + '.txt')).write_bytes(body)


def load(model_hash, observed, directory):
    if json.loads(game_catalog.forcing(model_hash)) != observed or 'disasterEvent' not in observed:
        raise ValueError('HISTORICAL_FORCING_INVALID')
    directory.mkdir(parents=True, exist_ok=True)
    (directory / 'forcing-catalog.json').write_bytes(game_catalog._read('catalog.json'))
    (directory / 'rainfall-source.json').write_bytes(read_source(observed['sourceRainfallFile'], observed['sourceRainfallSha256']))
    manifest_file = 'data/manifests/' + observed['rainfall']['sourceManifest']
    manifest = read_source(manifest_file, game_catalog.catalog()['sourceHashes'][manifest_file])
    (directory / 'rainfall-source-manifest.json').write_bytes(manifest)
    raw_rain = read_source('data/raw/' + observed['rainfall']['sourceManifest'].removesuffix('.json') + '.txt',
        observed['rainfall']['sourceHash'])
    (directory / 'rainfall-source.txt').write_bytes(raw_rain)
    catalogs, entries = {}, {}
    for name in ('evaporation', 'antecedent'):
        catalogs[name], entries[name] = game_catalog.climate_binding(name, model_hash)
        (directory / (name + '-catalog.json')).write_bytes(game_catalog._read(name + '.json'))
    reference = entries['evaporation']
    if not re.fullmatch(r'seoul-\d{8}-fao56-v1\.json', reference['file']):
        raise ValueError('HISTORICAL_PET_BINDING_INVALID')
    raw = read_source('data/derived/evaporation/' + reference['file'], reference['sha256'])
    evaporation = json.loads(raw)
    rain = observed['rainfall']
    if (reference['eventId'] != observed['disasterEvent']['id'] or evaporation['eventId'] != reference['eventId']
            or any(datetime.fromisoformat(evaporation[key]) != datetime.fromisoformat(rain[key]) for key in ('start', 'end'))
            or len(evaporation['ratesMmDay']) != len(rain['depthsMm'])):
        raise ValueError('HISTORICAL_PET_INPUT_INVALID')
    (directory / 'evaporation.json').write_bytes(raw)
    _weather_sources(evaporation, directory)
    for name, checksum in evaporation['implementationHashes'].items():
        if not re.fullmatch(r'[a-z_]+\.py', name):
            raise ValueError('HISTORICAL_PET_IMPLEMENTATION_INVALID')
        (directory / name).write_bytes(implementation_source(checksum))
    for module, checksum in catalogs['antecedent']['implementationHashes'].items():
        if not re.fullmatch(r'(engine|ingestion)/[a-z_]+\.py', module):
            raise ValueError('HISTORICAL_ANTECEDENT_IMPLEMENTATION_INVALID')
        (directory / ('antecedent-' + module.replace('/', '-'))).write_bytes(implementation_source(checksum))
    (directory / 'antecedent-generator.py').write_bytes(read_source('data/derived/antecedent/generator.py',
        catalogs['antecedent']['generatorSha256']))
    (directory / 'game-climate.py').write_bytes(Path(__file__).read_bytes())
    prior = {}
    reference = entries['antecedent']
    if reference['eventId'] != observed['disasterEvent']['id'] or reference['stationId'] != rain['stationId']:
        raise ValueError('HISTORICAL_ANTECEDENT_BINDING_INVALID')
    for kind in ('rainfall', 'evaporation'):
        item = reference[kind]
        if not re.fullmatch(r'seoul-\d{8}-(\d{1,5}-rain|pet)-v1\.json\.gz', item['file']):
            raise ValueError('HISTORICAL_ANTECEDENT_SOURCE_INVALID')
        raw = read_source('data/derived/antecedent/' + item['file'], item['sha256'])
        with gzip.GzipFile(fileobj=io.BytesIO(raw)) as compressed:
            body = compressed.read(16 * 1024**2 + 1)
        if len(body) > 16 * 1024**2:
            raise ValueError('HISTORICAL_ANTECEDENT_SOURCE_INVALID')
        prior[kind] = json.loads(body)
        (directory / item['file']).write_bytes(raw)
        _weather_sources(prior[kind], directory)
    start = datetime.fromisoformat(rain['start'])
    if (datetime.fromisoformat(prior['rainfall']['start']) != start - timedelta(days=7)
            or datetime.fromisoformat(prior['rainfall']['end']) != start
            or prior['rainfall']['stationId'] != rain['stationId'] or prior['rainfall']['intervalSeconds'] != 60
            or len(prior['rainfall']['depthsMm']) != 10080 or len(prior['evaporation']['ratesMmDay']) != 10080):
        raise ValueError('HISTORICAL_ANTECEDENT_TIME_INVALID')
    return evaporation, prior
