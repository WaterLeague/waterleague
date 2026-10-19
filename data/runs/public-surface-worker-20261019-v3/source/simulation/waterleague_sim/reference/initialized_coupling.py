"""실제 관측·문헌 시설과 명시적 합성 지형의 연속 초기화 진단."""
from copy import deepcopy

from waterleague_sim.reference.initialized_facilities import inputs as network_inputs
from waterleague_sim.reference.flood_cases import mesh
from waterleague_sim.forcing.coupled_initialization import METHOD
from waterleague_sim.forcing.surface_evaporation import TRANSFER
from waterleague_sim.engine.surface_exchange import DRY_EXCHANGE_POLICY


def inputs(design, *, days=7, step=60, antecedent_reference=None):
    import numpy as np
    network, rain, initialization = network_inputs(days, antecedent_reference=antecedent_reference)
    surface = mesh(2, 1, 200, 200, bed=lambda x, y: np.ones_like(x))
    network.update(coordinateSystem=surface['coordinateSystem'], verticalDatum=surface['verticalDatum'])
    text = network['inputText'].replace('OUT 0 FIXED 0 NO', 'OUT 0 FIXED 0 NO\nSURFACE 1 FIXED 1 NO')
    text = text.replace('[XSECTIONS]', 'INLET TANK SURFACE BOTTOM 1 0.65 NO 0\n[XSECTIONS]')
    text = text.replace('[REPORT]', 'INLET CIRCULAR 0.02 0 0 0\n[REPORT]')
    network['inputText'] = text
    surface.update(schemaVersion=2, startUtc=rain['startUtc'], durationSeconds=359*60,
                   maxStepSeconds=step, evidence='NUMERICAL_TEST_ONLY_NOT_SEOUL')
    surface['rainfallOwner'] = ['NETWORK', 'NETWORK', 'SURFACE', 'SURFACE']
    surface['infiltration'] = {'schemaVersion': 1, 'method': 'GREEN_AMPT', 'ownershipPolicy': 'SURFACE_ONLY',
        'initialization': 'EPA_INITIAL_DEFICIT_SEED', 'recoveryFactor': 1., 'imperviousTriangles': [],
        'evidence': 'EPA 토양 문헌 매개변수의 합성 지표 배정; 실측 토양/부지 아님',
        'regions': [{'triangles': [2, 3], 'perviousFraction': 1., 'suctionMm': 88.9,
            'conductivityMmH': 3.302, 'initialMoistureDeficit': .25,
            'evidence': '공개 토성 문헌값 진단; 합성 2ha 전면 투수 영역·명시적 초기 시드'}]}
    surface['evaporation'] = {'schemaVersion': 1, 'type': 'ARCHIVED_FAO56', 'ownershipPolicy': 'SURFACE_ONLY',
        'surfaceTransfer': TRANSFER, 'reference': rain['evaporationReference'],
        'evidence': '서울 108 관측 FAO-56의 표면별 미보정 전용'}
    rain['stationByTriangle'] = [None, None, '421', '421']
    model = {'schemaVersion': 1, 'evidence': 'NUMERICAL_TEST_ONLY_NOT_SEOUL', 'durationSeconds': 359*60,
        'maximumExchangeMilliseconds': step*1000, 'frameIntervalMilliseconds': 3600000,
        'dryExchangePolicy': DRY_EXCHANGE_POLICY,
        'network': network, 'surface': surface, 'networkRainfallTriangles': {'S1': [0, 1]},
        'ports': [{'id': 'inlet', 'outfall': 'SURFACE', 'orifice': 'INLET', 'crestM': 1.,
            'surfaceTriangles': [2, 3], 'evidence': '합성 수평 유입부; 실제 서울 시설 아님'}],
        'observedRainfall': rain, 'initialization': initialization | {'method': METHOD},
        'evaluationMetrics': {'schemaVersion': 1, 'policyVersion': 'OBSERVED_COUPLED_INITIALIZATION_TEST_v1',
            'evidence': 'NUMERICAL_TEST_ONLY_NOT_SEOUL', 'startMilliseconds': 0,
            'endMilliseconds': 359*60*1000, 'networkOutfalls': ['OUT'],
            'exposureTriangles': list(range(4)), 'wetDepthThresholdM': .001}}
    if design is not None:
        model['connectedFacilityDesign'] = deepcopy(design)
    return model
