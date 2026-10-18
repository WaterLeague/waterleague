"""덮개 강우·관망 역압용 명시적 수치 진단. 실제 서울 시설 아님."""
from .flood_cases import tank_input
from ..ingestion.published_network import digest


def source(*, backwater=False):
    text = tank_input(initial=.5 if backwater else 0, full=3, route_step=.01)
    text = text.replace('MINIMUM_STEP 0.01', 'MINIMUM_STEP 0.001\nSURCHARGE_METHOD SLOT\n'
        'MIN_SURFAREA 0.01\nHEAD_TOLERANCE 0.000001\nMAX_TRIALS 200\n'
        'INFILTRATION GREEN_AMPT\nWET_STEP 00:00:01\nDRY_STEP 00:00:01')
    if backwater: text = text.replace('OUT 0 FIXED 0 NO', 'OUT 0 FIXED 0.5 NO')
    return (text + '''
[RAINGAGES]
G INTENSITY 0:01 1 TIMESERIES RAIN
[TIMESERIES]
RAIN 01/01/2020 00:00 3600
RAIN 01/01/2020 00:01 0
RAIN 01/01/2020 00:02 0
[SUBCATCHMENTS]
S1 G TANK 0.01 100 10 1 0
[SUBAREAS]
S1 .013 .15 0 0 100 OUTLET
[INFILTRATION]
S1 50 4 .3
''').encode()


def design(raw, *, flap=True):
    return {'schemaVersion': 1, 'sourceNetworkSha256': digest(raw), 'id': 'Cistern',
        'subcatchmentId': 'S1', 'captureAreaM2': 20., 'footprintM2': 1., 'invertM': 0.,
        'depthAreaCurve': [{'depthM': 0., 'areaM2': 1.}, {'depthM': 1.4, 'areaM2': 1.}],
        'initialDepthM': 0.,
        'drain': {'crestM': .05, 'diameterM': .02, 'dischargeCoefficient': .65, 'flapGate': flap},
        'overflow': {'crestM': 1., 'diameterM': .1, 'dischargeCoefficient': .65, 'flapGate': flap},
        'evidence': 'NUMERICAL_DIAGNOSTIC_NOT_SEOUL_MEASUREMENT'}
