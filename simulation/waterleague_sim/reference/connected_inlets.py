"""EPA 공개 격자 유형의 수치 시험. 서울 도로·관망 관측 아님."""
from ..ingestion.published_network import digest


def case(*, placement='ON_GRADE', clogged=0., sewer_inflow=0., step=.1, street=False):
    surface_shape = 'STREET ROAD' if street else 'RECT_OPEN 1 2'
    raw = f'''[TITLE]
NUMERICAL_DIAGNOSTIC_NOT_SEOUL: explicit channel and sewer
[OPTIONS]
FLOW_UNITS CMS
FLOW_ROUTING DYNWAVE
START_DATE 01/01/2020
START_TIME 00:00:00
REPORT_START_DATE 01/01/2020
REPORT_START_TIME 00:00:00
END_DATE 01/01/2020
END_TIME 00:02:00
ROUTING_STEP {step}
MINIMUM_STEP 0.01
VARIABLE_STEP 0.75
MAX_TRIALS 40
HEAD_TOLERANCE 0.000001
REPORT_STEP 00:00:01
ALLOW_PONDING NO
[JUNCTIONS]
A 1.5 1 0 0 0
B 1 1 0 0 0
S 0.9 0.1 0 0 0
[OUTFALLS]
BYPASS 0.5 FREE NO
SEWER 0 FREE NO
[CONDUITS]
CHANNEL A B 50 0.016 0 0 0 0
CONTINUATION B BYPASS 50 0.016 0 0 0 0
PIPE S SEWER 50 0.013 0 0 0 0
[XSECTIONS]
CHANNEL {surface_shape} 0 0
CONTINUATION {surface_shape} 0 0
PIPE CIRCULAR 0.1 0 0 0
[STREETS]
ROAD 4 0.15 2 0.016 0 0 1 0 0 0
[DWF]
A FLOW 0.05
S FLOW {sewer_inflow}
[REPORT]
NODES ALL
LINKS ALL
'''.encode()
    design = {'schemaVersion': 1, 'sourceNetworkSha256': digest(raw), 'placements': [{
        'id': 'Grate', 'facilityType': 'STORM_INLET', 'basis': 'EXPLICIT_DESIGN_NOT_SITE_MEASURED',
        'evidence': '명시적 수치 시험·EPA 공개 2ft 격자 예시 치수·서울 현장 아님',
        'conduitId': 'CHANNEL', 'captureNodeId': 'S',
        'shape': {'type': 'GRATE' if street else 'DROP_GRATE', 'lengthM': .6096,
                  'widthM': .6096, 'grateType': 'P_BAR-30'},
        'numberPerSide': 1, 'cloggedPercent': clogged, 'flowLimitM3s': 0.,
        'localDepressionM': 0., 'localWidthM': 0., 'placement': placement}]}
    return raw, design
