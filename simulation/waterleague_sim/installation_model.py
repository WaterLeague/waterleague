"""현재 게임 설치의 원형 공간·공통 설계 조건·관측소 결속."""
import copy
import json
from .spatial import game_catalog
from .spatial.play_bundle import open_catalog


def resolve(installation):
    registry = game_catalog.regions()
    district = installation.get('district_id')
    if district not in registry:
        raise ValueError('LIVE_DISTRICT_INVALID')
    catalog = open_catalog()
    if (not catalog.accepts_catalog(installation.get('model_hash'), installation.get('cell_id'))
            or not catalog.accepts_catalog(registry[district]['siteCatalogSha256'])):
        raise ValueError('LIVE_INSTALLATION_MODEL_INVALID')
    model = catalog.model(installation.get('cell_id'), district=district)
    model['mapId'] = 'seoul-ngii-v1-' + district
    policy = installation.get('budget_policy')
    if policy is not None:
        if isinstance(policy, str):
            policy = json.loads(policy)
        expected = model['budgetPolicy']
        if (not isinstance(policy, dict) or policy != expected
                or policy.get('ruleVersion') != 'SEOUL_PERSONAL_FULL_2026_V3'
                or policy.get('personalLimitKrw') != 2_000_000_000 or policy.get('allocationScope') != 'MEMBER'):
            raise ValueError('LIVE_BUDGET_POLICY_INVALID')
        model['budgetPolicy'] = copy.deepcopy(policy)
    station = registry[district]['defaultRainfall']
    if not station.get('stationId') or not station.get('stationName'):
        raise ValueError('LIVE_STATION_BINDING_INVALID')
    return model, station['stationId'], station['stationName']


def with_observed_forcing(model, evaporation):
    if not evaporation.get('method') or not evaporation.get('sourceHashes'):
        raise ValueError('LIVE_EVAPORATION_EVIDENCE_MISSING')
    value = copy.deepcopy(model)
    value['assumptions'] = [item for item in value['assumptions'] if not item.startswith('증발 0 가정')]
    value['assumptions'] += ['강우와 증발산은 관측 입력과 공개 기상 산정률 사용',
        '공통 토양·경사·재료·직접 강우는 설계 비교 조건이며 현장 관측·배수 연결 미확인']
    return value
