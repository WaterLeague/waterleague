"""실제 2022 관측과 합성 2ha 유역의 연결 시설 초기화 비교 입력."""
from datetime import datetime, timedelta, timezone
from copy import deepcopy
import hashlib

from waterleague_sim.engine.swmm import ROOT
from waterleague_sim.forcing.network_initialization import METHOD


def inputs(days=7, *, antecedent_reference=None):
    if days not in (7, 14, 28):
        raise ValueError('초기화 비교 기간 오류')
    start=datetime(2022,8,8,9,tzinfo=timezone.utc)-timedelta(days=days)
    end=datetime(2022,8,8,14,59,1,tzinfo=timezone.utc)
    text=f'''[TITLE]
NUMERICAL_TEST_ONLY: observed weather, synthetic catchment and network
[OPTIONS]
FLOW_UNITS CMS
FLOW_ROUTING DYNWAVE
INFILTRATION GREEN_AMPT
START_DATE {start:%m/%d/%Y}
START_TIME {start:%H:%M:%S}
REPORT_START_DATE {start:%m/%d/%Y}
REPORT_START_TIME {start:%H:%M:%S}
END_DATE {end:%m/%d/%Y}
END_TIME {end:%H:%M:%S}
WET_STEP 00:00:01
DRY_STEP 00:00:01
ROUTING_STEP 1
MINIMUM_STEP 0.01
VARIABLE_STEP 0
MIN_SURFAREA 0.01
HEAD_TOLERANCE 0.000001
MAX_TRIALS 40
REPORT_STEP 01:00:00
ALLOW_PONDING NO
[SUBCATCHMENTS]
S1 G TANK 2 80 100 1 0
[SUBAREAS]
S1 0.013 0.15 1 2 25 OUTLET
[INFILTRATION]
S1 50 4 0.3
[STORAGE]
TANK 0 10 0 FUNCTIONAL 0 0 1000 0 1
[OUTFALLS]
OUT 0 FIXED 0 NO
[ORIFICES]
DRAIN TANK OUT BOTTOM 0 0.65 NO 0
[XSECTIONS]
DRAIN CIRCULAR 0.3 0 0 0
[REPORT]
NODES ALL
LINKS ALL
'''
    model={'inputText':text,'timeZone':'UTC','evidence':'SYNTHETIC_HYDRAULICS_NOT_SEOUL'}
    name='seoul-20220808-fao56-v1.json'
    spec={'schemaVersion':1,'startUtc':'2022-08-08T09:00:00+00:00','endUtc':'2022-08-08T14:59:00+00:00',
      'assignmentEvidence':'실제 성동 관측의 합성 2ha 집수 배정; 서울 현장 모형 아님',
      'stationByCatchment':{'S1':'421'},'stations':[{'file':'kma-421-202208081800-202208082359-disaster-v1.json','sha256':'21d21033308e31deafe9190f5a0723fded9e43562a0d7c5573cc94c3e99efd96'}],
      'evaporationReference':{'file':name,'sha256':hashlib.sha256((ROOT/'data/derived/evaporation'/name).read_bytes()).hexdigest()}}
    ref={'file':'seoul-20220808-421-14d-v1.json.gz','sha256':'95c290cbbaaee551c73e3f24795605945bcc4d978b2b6c225392f5aef1f7fe98'}
    if antecedent_reference is not None:
        ref = deepcopy(antecedent_reference)
    init={'schemaVersion':1,'method':METHOD,'days':days,'stations':[ref],'weatherReference':ref,'evidence':'실제 선행 강우·기상의 문헌 설계 초기화; 현장 관측 상태 아님'}
    return model,spec,init
