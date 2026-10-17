"""공동 설치의 불변 공개 후보와 설치 당시 물리 경계 연결."""
import copy
import gzip
import json
from functools import lru_cache
from .engine.continuous import ROOT, digest
from .model_catalog import read_catalog

CATALOG_HASHES={1:'f26b639dbdb2fee3c1aff172a19153868a07aa70735a6dfcfda863c3a38e8b64',
                2:'009fcd085f476bbc96a41888646f284942cd69aae0b9405defcb2764a8d6d5ea',
                3:'80e46a9c3821cdeff4b9acd839b264d810ba559202da828cdb8a6b45c04b15e4'}

@lru_cache(maxsize=3)
def site_catalog(version=3):
    path=ROOT/'backend/src/main/resources/shared-sites'/('catalog.json' if version==1 else f'catalog-v{version}.json')
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
def candidate_snapshot(district, version=3):
    districts,_,_=catalog();entry=site_catalog(version)[district]
    if entry['file']!=f'{district}-v{version}.json.gz':raise ValueError('LIVE_CATALOG_INVALID')
    raw=(ROOT/'backend/src/main/resources/shared-sites'/entry['file']).read_bytes()
    if digest(raw)!=entry['gzipSha256']:raise ValueError('LIVE_CATALOG_INVALID')
    decoded=gzip.decompress(raw)
    if digest(decoded)!=entry['sha256']:raise ValueError('LIVE_CATALOG_INVALID')
    snapshot=json.loads(decoded)
    if snapshot['baseModelHash']!=districts[district]['defaultModelHash']:raise ValueError('LIVE_MODEL_LINK_INVALID')
    return snapshot

def candidates(district, version=3):
    return {c['id']:c for c in candidate_snapshot(district, version)['cells']}

def resolve(installation):
    districts,sites,models=catalog();district=districts[installation['district_id']]
    model=json.loads(models[district['defaultModelHash']]);version=0
    if installation['model_hash']==district['defaultModelHash']:
        cell=next(c for c in model['cells'] if c['id']==installation['cell_id'])
    else:
        version=next((v for v in (3,2,1) if site_catalog(v)[district['districtId']]['sha256']==installation['model_hash']),None)
        if version is None:raise ValueError('LIVE_INSTALLATION_MODEL_INVALID')
        cell=candidates(district['districtId'],version)[installation['cell_id']]
    model['cells']=[copy.deepcopy(cell)]
    model['sharedSiteSource']={'districtId':district['districtId'],'siteCatalogHash':installation['model_hash'],
        'baseModelHash':district['defaultModelHash'],'constraintVersion':version,
        'inflowPolicy':'DIRECT_RAINFALL_ONLY' if version>=2 else 'LEGACY_ALL_IMPERVIOUS_RUNOFF'}
    if version>=2:
        model['assumptions']=[s for s in model['assumptions'] if '60%' not in s and '80%' not in s]
        model['assumptions']+=['공개 도형 면적 기준의 계산 경계; 실제 시공 가능 면적 미확인',
            '배수 연결 미확인으로 시설 자체 강우만 처리; 외부 유입 없음']
    if version>=3:
        source=candidate_snapshot(district['districtId'],version)
        for key in ('unitCosts','costModel','costSourceSha256','budget','budgetPolicy'):
            model[key]=copy.deepcopy(source[key])
    if installation.get('budget_policy') is not None:
        policy = installation['budget_policy']
        if isinstance(policy,str): policy = json.loads(policy)
        if (policy.get('ruleVersion') != 'SEOUL_DISTRICT_EQUAL_2026_V2'
                or policy.get('districtCount') != 25 or policy.get('districtLimitKrw') != 80000000
                or policy.get('limitKrw') != 2000000000):
            raise ValueError('LIVE_BUDGET_POLICY_INVALID')
        model['budget'] = policy['districtLimitKrw']
        model['budgetPolicy'] = copy.deepcopy(policy)
    # 현재/재해 강우를 별도로 연결하므로 기본 모델의 과거 관측 창 설명은 상속하지 않는다.
    model['assumptions']=[a for a in model['assumptions']
        if not a.startswith(('2026 공개 형상에서 2024', '2024-07-18'))
        and not (version>=2 and a.startswith('선정 표면의 잔여 불투수면 유출 전량'))]
    model.pop('rainfall',None)
    station=district.get('defaultRainfall') or {}
    return model,str(station.get('stationId','110')),station.get('stationName','강서')


def with_observed_forcing(model, evaporation):
    if not evaporation.get('method') or not evaporation.get('sourceHashes'):
        raise ValueError('LIVE_EVAPORATION_EVIDENCE_MISSING')
    value = copy.deepcopy(model)
    value['assumptions'] = [a for a in value['assumptions'] if not a.startswith('증발 0 가정')]
    value['assumptions'] += [
        '강우는 계산 기간의 관측 입력, 증발산은 관측 기상에서 산정한 분별 적용률 사용',
        '불투수율·경사·유출 폭·시설 재료는 관측 강우와 별개인 모델 입력; 실측으로 자동 변환되지 않음',
    ]
    return value
