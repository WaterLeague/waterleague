"""공동 설치의 불변 공개 후보와 설치 당시 물리 경계 연결."""
import copy
import gzip
import json
from functools import lru_cache
from .engine.continuous import ROOT, digest
from .model_catalog import read_catalog

CATALOG_HASHES={1:'f26b639dbdb2fee3c1aff172a19153868a07aa70735a6dfcfda863c3a38e8b64',
                2:'009fcd085f476bbc96a41888646f284942cd69aae0b9405defcb2764a8d6d5ea'}

@lru_cache(maxsize=2)
def site_catalog(version=2):
    path=ROOT/'backend/src/main/resources/shared-sites'/('catalog.json' if version==1 else 'catalog-v2.json')
    raw=path.read_bytes()
    if digest(raw)!=CATALOG_HASHES[version]:raise ValueError('LIVE_CATALOG_INVALID')
    return {s['districtId']:s for s in json.loads(raw)['entries']}

@lru_cache(maxsize=1)
def catalog():
    districts=(ROOT/'backend/src/main/resources/districts/seoul-play-v2.json').read_bytes()
    if digest(districts)!='4187dbcf06bbcf0cb36212ae6d983969098ab9d947afe083702487e3ec910121':
        raise ValueError('LIVE_CATALOG_INVALID')
    return ({d['districtId']:d for d in json.loads(districts)['regions']},site_catalog(),read_catalog(ROOT/'data/models'))

@lru_cache(maxsize=4)
def candidates(district, version=2):
    districts,_,_=catalog();entry=site_catalog(version)[district]
    if entry['file']!=f'{district}-v{version}.json.gz':raise ValueError('LIVE_CATALOG_INVALID')
    raw=(ROOT/'backend/src/main/resources/shared-sites'/entry['file']).read_bytes()
    if digest(raw)!=entry['gzipSha256']:raise ValueError('LIVE_CATALOG_INVALID')
    decoded=gzip.decompress(raw)
    if digest(decoded)!=entry['sha256']:raise ValueError('LIVE_CATALOG_INVALID')
    snapshot=json.loads(decoded)
    if snapshot['baseModelHash']!=districts[district]['defaultModelHash']:raise ValueError('LIVE_MODEL_LINK_INVALID')
    return {c['id']:c for c in snapshot['cells']}

def resolve(installation):
    districts,sites,models=catalog();district=districts[installation['district_id']]
    model=json.loads(models[district['defaultModelHash']]);version=0
    if installation['model_hash']==district['defaultModelHash']:
        cell=next(c for c in model['cells'] if c['id']==installation['cell_id'])
    else:
        version=next((v for v in (2,1) if site_catalog(v)[district['districtId']]['sha256']==installation['model_hash']),None)
        if version is None:raise ValueError('LIVE_INSTALLATION_MODEL_INVALID')
        cell=candidates(district['districtId'],version)[installation['cell_id']]
    model['cells']=[copy.deepcopy(cell)]
    model['sharedSiteSource']={'districtId':district['districtId'],'siteCatalogHash':installation['model_hash'],
        'baseModelHash':district['defaultModelHash'],'constraintVersion':version,
        'inflowPolicy':'DIRECT_RAINFALL_ONLY' if version==2 else 'LEGACY_ALL_IMPERVIOUS_RUNOFF'}
    if version==2:
        model['assumptions']=[s for s in model['assumptions'] if '60%' not in s and '80%' not in s]
        model['assumptions']+=['공개 도형 면적 기준의 계산 경계; 실제 시공 가능 면적 미확인',
            '배수 연결 미확인으로 시설 자체 강우만 처리; 외부 유입 없음']
    model.pop('rainfall',None)
    station=district.get('defaultRainfall') or {}
    return model,str(station.get('stationId','110')),station.get('stationName','강서')
