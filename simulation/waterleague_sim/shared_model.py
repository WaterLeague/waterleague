"""공동 설치의 불변 공개 후보와 설치 당시 물리 경계 연결."""
import copy
import gzip
import json
from functools import lru_cache
from .engine.continuous import ROOT, digest
from .model_catalog import read_catalog

CATALOG_HASHES={8:'d58dbf9cf2d6b44342c8ca468d7d5d4f8d4145ef3946fd8d5789b8cacebab8d9',7:'de9a1bf428d4bd52604744213a33d5fa26fea84cab9297668064d58eb0be7469',6:'18a22093b2541ab05ed3fdee6a394a998bbfd5d092c6105cf787702f99bdf501',5:'450f016165b58477ba4fb09eb81aec08de93d6081cd367ddf9b906920d7c6e07',4:'f1f8d5f366cf47fff86319b27669bfb8e4a1fd3912d701b70b4b6e280e6fa66f',1:'f26b639dbdb2fee3c1aff172a19153868a07aa70735a6dfcfda863c3a38e8b64',
                2:'009fcd085f476bbc96a41888646f284942cd69aae0b9405defcb2764a8d6d5ea',
                3:'80e46a9c3821cdeff4b9acd839b264d810ba559202da828cdb8a6b45c04b15e4'}

@lru_cache(maxsize=8)
def site_catalog(version=8):
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
def candidate_snapshot(district, version=8):
    districts,_,_=catalog();entry=site_catalog(version)[district]
    if entry['file']!=f'{district}-v{version}.json.gz':raise ValueError('LIVE_CATALOG_INVALID')
    raw=(ROOT/'backend/src/main/resources/shared-sites'/entry['file']).read_bytes()
    if digest(raw)!=entry['gzipSha256']:raise ValueError('LIVE_CATALOG_INVALID')
    decoded=gzip.decompress(raw)
    if digest(decoded)!=entry['sha256']:raise ValueError('LIVE_CATALOG_INVALID')
    snapshot=json.loads(decoded)
    if snapshot['baseModelHash']!=districts[district]['defaultModelHash']:raise ValueError('LIVE_MODEL_LINK_INVALID')
    return snapshot

def candidates(district, version=8):
    return {c['id']:c for c in candidate_snapshot(district, version)['cells']}

def resolve(installation):
    districts,sites,models=catalog();district=districts[installation['district_id']]
    model=json.loads(models[district['defaultModelHash']]);version=0
    if installation['model_hash']==district['defaultModelHash']:
        cell=next(c for c in model['cells'] if c['id']==installation['cell_id'])
    else:
        version=next((v for v in (8,7,6,5,4,3,2,1) if site_catalog(v)[district['districtId']]['sha256']==installation['model_hash']),None)
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
    if version >= 4:
        model['physicsEvidence'] = copy.deepcopy(candidate_snapshot(district['districtId'],version)['physicsEvidence'])
        physical = model['cells'][0]['physicalInputs']
        model['assumptions'] = [a for a in model['assumptions'] if not a.startswith('불투수율 100%')]
        model['assumptions'] += [
            '유출 폭은 공개 도형 면적/장축으로 산정; 배수구 방향 미확인, 부분 설치는 같은 종횡비 축소',
            '기준 표면의 불투수율 100%는 옥상·포장면 분류의 모델 조건이며 실측 비율 아님',
            ('지상 경사는 2025 공개 DEM 90m 격자의 270m 창 지역 경사 대용값; 개별 포장면 실측 아님'
             if physical['slopeMethod']=='NGII_2025_90M_HORN_TERRAIN_PROXY' else '표면 경사 자료 미확보: 1% 설계 가정 잔존'),
            ('원지반 침투는 공개 심토토성군과 EPA 문헌 범위의 낮은 투수계수 시나리오; 성토·다짐 미확인'
             if physical['soilStatus']=='TEXTURE_CLASS_LITERATURE_ESTIMATE' else '원지반 토성 미확인 또는 옥상 비적용; 기존 설계 조건 유지'),
        ]
    if version >= 5:
        source = candidate_snapshot(district['districtId'], version)
        for key in ('facilityDesignSet', 'initializationPolicy'):
            model[key] = copy.deepcopy(source[key])
        model['assumptions'] += ['시설 재료는 EPA 공개 제원 범위 안에서 선택한 설계값이며 서울 현장 실측값 아님']
    if version >= 6 and 'RAIN_GARDEN' in cell['allowedTypes']:
        model['assumptions'] += ['빗물정원은 차수막 없는 설계의 하부 침투 경계 연결; 현장 차수막·지하수·다짐 미확인']
    if installation.get('budget_policy') is not None:
        policy = installation['budget_policy']
        if isinstance(policy,str): policy = json.loads(policy)
        if policy.get('ruleVersion') == 'SEOUL_DISTRICT_EQUAL_2026_V2':
            if policy.get('districtCount') != 25 or policy.get('districtLimitKrw') != 80000000 or policy.get('limitKrw') != 2000000000:
                raise ValueError('LIVE_BUDGET_POLICY_INVALID')
            model['budget'] = policy['districtLimitKrw']
        elif policy.get('ruleVersion') == 'SEOUL_PERSONAL_FULL_2026_V3':
            if policy.get('personalLimitKrw') != 2000000000 or policy.get('limitKrw') != 2000000000 or policy.get('allocationScope') != 'MEMBER':
                raise ValueError('LIVE_BUDGET_POLICY_INVALID')
            model['budget'] = policy['personalLimitKrw']
        else:
            raise ValueError('LIVE_BUDGET_POLICY_INVALID')
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
