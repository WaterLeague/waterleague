"""공동 설치의 불변 공개 후보와 기존 설계 조건 연결."""
import copy
import gzip
import json
from functools import lru_cache

from .engine.continuous import ROOT, digest
from .model_catalog import read_catalog


@lru_cache(maxsize=1)
def catalog():
    directory = ROOT/'backend/src/main/resources'
    districts = (directory/'districts/seoul-play-v2.json').read_bytes()
    sites = (directory/'shared-sites/catalog.json').read_bytes()
    if (digest(districts) != '4187dbcf06bbcf0cb36212ae6d983969098ab9d947afe083702487e3ec910121'
            or digest(sites) != 'f26b639dbdb2fee3c1aff172a19153868a07aa70735a6dfcfda863c3a38e8b64'):
        raise ValueError('LIVE_CATALOG_INVALID')
    return ({d['districtId']: d for d in json.loads(districts)['regions']},
            {s['districtId']: s for s in json.loads(sites)['entries']},
            read_catalog(ROOT/'data/models'))


@lru_cache(maxsize=2)
def candidates(district):
    districts, sites, _ = catalog()
    entry = sites[district]
    if entry['file'] != district+'-v1.json.gz':
        raise ValueError('LIVE_CATALOG_INVALID')
    raw = (ROOT/'backend/src/main/resources/shared-sites'/entry['file']).read_bytes()
    if digest(raw) != entry['gzipSha256']:
        raise ValueError('LIVE_CATALOG_INVALID')
    decoded = gzip.decompress(raw)
    if digest(decoded) != entry['sha256']:
        raise ValueError('LIVE_CATALOG_INVALID')
    snapshot = json.loads(decoded)
    if snapshot['baseModelHash'] != districts[district]['defaultModelHash']:
        raise ValueError('LIVE_MODEL_LINK_INVALID')
    return {c['id']: c for c in snapshot['cells']}


def resolve(installation):
    districts, sites, models = catalog()
    district = districts[installation['district_id']]
    model = json.loads(models[district['defaultModelHash']])
    if installation['model_hash'] == district['defaultModelHash']:
        cell = next(c for c in model['cells'] if c['id'] == installation['cell_id'])
    elif installation['model_hash'] == sites[district['districtId']]['sha256']:
        cell = candidates(district['districtId'])[installation['cell_id']]
    else:
        raise ValueError('LIVE_INSTALLATION_MODEL_INVALID')
    model['cells'] = [copy.deepcopy(cell)]
    model['sharedSiteSource'] = {'districtId': district['districtId'],
                               'siteCatalogHash': installation['model_hash'],
                               'baseModelHash': district['defaultModelHash']}
    model.pop('rainfall', None)
    station = district.get('defaultRainfall') or {}
    return model, str(station.get('stationId', '110')), station.get('stationName', '강서')
