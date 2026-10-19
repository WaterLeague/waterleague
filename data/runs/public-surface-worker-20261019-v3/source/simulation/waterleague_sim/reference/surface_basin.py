"""개방 저류지와 주변 월류·관망 역류의 수치 시험 설계."""
import hashlib

from waterleague_sim.engine.swmm import ROOT
from waterleague_sim.evaluation.values import digest
from waterleague_sim.forcing.surface_evaporation import TRANSFER
from waterleague_sim.reference.flood_cases import coupled_case


def case(*, sealed=False, exchange_ms=100, initial_network=2., route_ms=10):
    model = coupled_case(nx=8, exchange_ms=exchange_ms, initial_network=initial_network)
    surface = model['surface']
    count = len(surface['triangles'])
    surface.update(schemaVersion=2, startUtc='2022-08-08T09:00:00+00:00', durationSeconds=120)
    surface['manningN'] = [.02]*count
    surface['infiltration'] = {'schemaVersion': 2, 'method': 'GREEN_AMPT', 'ownershipPolicy': 'SURFACE_ONLY',
        'initialization': 'EPA_INITIAL_DEFICIT_SEED', 'recoveryFactor': 1.,
        'partitionPolicy': 'EXPLICIT_AREA_FRACTIONS', 'evidence': '수치 시험의 차수 표면',
        'regions': [], 'imperviousRegions': [{'triangles': list(range(count)), 'areaFraction': 1.,
                                             'evidence': '수치 시험의 차수 표면'}]}
    filename = 'seoul-20220808-fao56-v1.json'
    surface['evaporation'] = {'schemaVersion': 1, 'type': 'ARCHIVED_FAO56', 'ownershipPolicy': 'SURFACE_ONLY',
        'surfaceTransfer': TRANSFER, 'reference': {'file': filename,
            'sha256': hashlib.sha256((ROOT/'data/derived/evaporation'/filename).read_bytes()).hexdigest()},
        'evidence': '서울 108 관측 기반 기준 증발산의 미보정 지표 적용'}
    text = model['network']['inputText'].replace('01/01/2020', '08/08/2022')
    text = text.replace('START_TIME 00:00:00', 'START_TIME 09:00:00').replace('END_TIME 00:02:01', 'END_TIME 09:02:01')
    if route_ms != 10:
        if type(route_ms) is not int or not 1 <= route_ms <= 10:
            raise ValueError('수치 진단 시간 간격 범위 오류')
        text = text.replace('ROUTING_STEP 0.01', f'ROUTING_STEP {route_ms/1000}').replace(
            'MINIMUM_STEP 0.01', f'MINIMUM_STEP {route_ms/1000}').replace('MAX_TRIALS 40', 'MAX_TRIALS 200')
    model['network']['inputText'] = text
    model['network']['timeZone'] = 'UTC'
    model['ports'][0]['surfaceTriangles'] = [0, 1]
    cells = [i for i, triangle in enumerate(surface['triangles'])
             if all(.5 <= surface['verticesM'][j][0] <= 1.5 and .5 <= surface['verticesM'][j][1] <= 1.5
                    for j in triangle)]
    vertices = sorted({j for i in cells for j in surface['triangles'][i]})
    heights = [{'vertex': j, 'elevationM': 1. if any(v in (.5, 1.5) for v in surface['verticesM'][j]) else .2}
               for j in vertices]
    floor = {row['vertex'] for row in heights if row['elevationM'] == .2}
    drain_cells = [i for i in cells if set(surface['triangles'][i]) <= floor]
    model['surfaceRainfall'] = [{'timeMilliseconds': 0, 'ratesMmH': [60.]*count,
                                'evidence': 'NUMERICAL_TEST_ONLY_CONSTANT_RAIN_NOT_OBSERVATION'}]
    model['evaluationMetrics'] = {'schemaVersion': 1, 'policyVersion': 'SURFACE_BASIN_TEST_v1',
        'evidence': 'NUMERICAL_TEST_ONLY_NOT_SEOUL', 'startMilliseconds': 0, 'endMilliseconds': 120000,
        'networkOutfalls': ['OUT'], 'exposureTriangles': [i for i in range(count) if i not in cells],
        'wetDepthThresholdM': .001}
    model['surfaceBasinDesign'] = {'schemaVersion': 2, 'sourceModelSha256': digest(model), 'placements': [{
        'id': 'Pond', 'facilityType': 'RETENTION_BASIN', 'basis': 'EXPLICIT_DESIGN_NOT_SITE_MEASURED',
        'evidence': '합성 1m² 절토·0.8m 바닥·수평 배수구의 수치 진단', 'triangles': cells,
        'vertexElevations': heights,
        'material': {'manningN': .03, 'lining': 'SEALED' if sealed else 'PERMEABLE',
            'soil': None if sealed else {'suctionMm': 88.9, 'conductivityMmH': 3.302, 'initialMoistureDeficit': .25},
            'evidence': '문헌 토양 매개변수의 명시적 설계·현장 토성 관측 아님'},
        'drain': {'nodeId': 'TANK', 'triangles': drain_cells, 'crestM': .25, 'diameterM': .08,
            'dischargeCoefficient': .65, 'evidence': '명시적 국부 개구부 설계; 실제 서울 시설 아님'}}]}
    return model


def observed_case():
    model = case(initial_network=0.)
    design = model.pop('surfaceBasinDesign')
    model.pop('surfaceRainfall')
    model['observedRainfall'] = {'schemaVersion': 1, 'startUtc': '2022-08-08T09:00:00+00:00',
        'endUtc': '2022-08-08T09:02:00+00:00', 'stationByTriangle': ['421']*len(model['surface']['triangles']),
        'assignmentEvidence': '실제 성동 421의 2분 관측을 합성 격자에 적용; 서울 유역 재현 아님',
        'stations': [{'file': 'kma-421-202208081800-202208082359-disaster-v1.json',
            'sha256': '21d21033308e31deafe9190f5a0723fded9e43562a0d7c5573cc94c3e99efd96'}]}
    design['sourceModelSha256'] = digest(model)
    model['surfaceBasinDesign'] = design
    return model


def initialized_case():
    from waterleague_sim.reference.initialized_coupling import inputs
    model = inputs(None)
    reference = case(initial_network=0.)
    design = reference['surfaceBasinDesign']
    cells = design['placements'][0]['triangles']
    surface = reference['surface']
    surface['verticesM'] = [[100*x, 100*y] for x, y in surface['verticesM']]
    surface.update(durationSeconds=model['durationSeconds'], maxStepSeconds=60)
    owners = ['SURFACE' if i in cells else 'NETWORK' for i in range(len(surface['triangles']))]
    surface['rainfallOwner'] = owners
    surface['infiltration']['imperviousRegions'][0]['triangles'] = cells[:]
    model['surface'] = surface
    model['network']['inputText'] = model['network']['inputText'].replace('S1 G TANK 2 80 100 1 0',
                                                                        'S1 G TANK 3 80 100 1 0')
    model['networkRainfallTriangles'] = {'S1': [i for i, owner in enumerate(owners) if owner == 'NETWORK']}
    model['ports'][0]['surfaceTriangles'] = [0, 1]
    model['observedRainfall']['stationByTriangle'] = ['421' if owner == 'SURFACE' else None for owner in owners]
    model['evaluationMetrics']['exposureTriangles'] = model['networkRainfallTriangles']['S1'][:]
    design['placements'][0]['evidence'] = '합성 1ha 절토 저류지·3ha 관망 유역의 관측 선행 입력 진단'
    design['sourceModelSha256'] = digest(model)
    model['surfaceBasinDesign'] = design
    return model
