"""공개 펌프 성능곡선의 수치 진단 관망. 서울 실제 시설과 구분."""
from ..engine.connected_pumps import CATALOG_HASH, catalog
from ..ingestion.published_network import digest


def case(*, tail=5, initial=2, seconds=600, step=.05, length=10, pressure_limit=20):
    text = f'''[TITLE]
Synthetic pump delivery; public manufacturer curve; not a Seoul asset
[OPTIONS]
FLOW_UNITS CMS
FLOW_ROUTING DYNWAVE
START_DATE 01/01/2022
START_TIME 00:00:00
REPORT_START_DATE 01/01/2022
REPORT_START_TIME 00:00:00
END_DATE 01/01/2022
END_TIME 00:{seconds//60:02d}:{seconds%60:02d}
REPORT_STEP 00:00:01
ROUTING_STEP {step}
MINIMUM_STEP {step}
VARIABLE_STEP 0
MAX_TRIALS 200
HEAD_TOLERANCE .0001
SURCHARGE_METHOD SLOT
ALLOW_PONDING NO
[STORAGE]
S 0 5 {initial} FUNCTIONAL 0 0 100 0 0
R 4 10 {tail-4} FUNCTIONAL 0 0 1000 0 0
[OUTFALLS]
O 4 FIXED {tail} NO
[ORIFICES]
BYPASS S R SIDE 4 .65 YES 0
[CONDUITS]
TAIL R O 10 .014 0 0
[XSECTIONS]
BYPASS CIRCULAR .01 0 0 0
TAIL CIRCULAR 2 0 0 0 1
[REPORT]
NODES ALL
LINKS ALL
'''.encode()
    evidence = '명시적 수치 시험 설계; 서울 시설의 실측 치수·재료 아님'
    design = {'schemaVersion': 1, 'sourceNetworkSha256': digest(text), 'curveCatalogHash': CATALOG_HASH,
        'placements': [{'id': 'Lift', 'facilityType': 'PUMP_STATION', 'basis': 'EXPLICIT_DESIGN_NOT_SITE_MEASURED',
            'evidence': evidence, 'curveId': catalog()['id'], 'fromNode': 'S', 'toNode': 'R',
            'startDepthM': 1.8, 'stopDepthM': 1.2, 'initialStatus': 'OFF',
            'delivery': {'lengthM': length, 'diameterM': .5, 'roughnessMm': .1,
                'pressureHeadLimitM': pressure_limit, 'entranceLoss': .5, 'exitLoss': 1, 'averageLoss': 0,
                'checkValve': True,
                'evidence': evidence}}]}
    return text, design
