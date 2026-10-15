"""EPA C API 기반 실행. 사용자 INP·경로·엔진 매개변수 수신 금지."""
import ctypes as C
import hashlib
import json
import math
import os
import platform
import re
from datetime import datetime,timedelta
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
REVISION='7952ca837988b1c32f791812eccc9fd64547e093'
class SimulationQualityError(ValueError):pass

def library_path():
 name='libswmm5.dylib' if platform.system()=='Darwin' else 'libswmm5.so'
 return Path(os.environ.get('SWMM_LIBRARY',ROOT/'tmp/swmm-build/install/bin'/name))

def make_input(model,placements,conductivity_factor=1.0,step_seconds=10):
 rain=model['rainfall'];start=datetime.fromisoformat(rain['start']);end=datetime.fromisoformat(rain['end'])
 h=model['hydrology'];sections={}
 sections['TITLE']=['WATER LEAGUE EXPLORATORY; NOT A SITE-VALIDATED DRAINAGE MODEL']
 sections['OPTIONS']=[f'FLOW_UNITS CMS','INFILTRATION GREEN_AMPT','FLOW_ROUTING KINWAVE',
  f'START_DATE {start:%m/%d/%Y}',f'START_TIME {start:%H:%M:%S}',f'REPORT_START_DATE {start:%m/%d/%Y}',f'REPORT_START_TIME {start:%H:%M:%S}',
  f'END_DATE {end:%m/%d/%Y}',f'END_TIME {end:%H:%M:%S}',f'WET_STEP 00:00:{step_seconds:02}',f'DRY_STEP 00:00:{step_seconds:02}',
  'REPORT_STEP 00:01:00',f'ROUTING_STEP {step_seconds}','ALLOW_PONDING NO','THREADS 1']
 sections['EVAPORATION']=[f'CONSTANT {h["evaporationMmDay"]}']
 interval=rain['intervalSeconds'];sections['RAINGAGES']=[f'RAIN VOLUME {interval//3600}:{interval%3600//60:02} 1 TIMESERIES RAIN_DATA']
 sections['OUTFALLS']=['OUT 0 FREE NO']
 sections['SUBCATCHMENTS']=[];sections['SUBAREAS']=[];sections['INFILTRATION']=[]
 byid={p['cellId']:p for p in placements}
 for c in model['cells']:
  cid=c['id'];area=c['areaM2'];sections['SUBCATCHMENTS'].append(f'{cid} RAIN OUT {area/10000:.8f} {h["imperviousPercent"]} {math.sqrt(area):.6f} {h["slopePercent"]} 0')
  sections['SUBAREAS'].append(f'{cid} {h["nImpervious"]} 0.2 {h["depressionMm"]} 5 0 OUTLET 100')
  sections['INFILTRATION'].append(f'{cid} {h["suctionMm"]} {h["conductivityMmH"]*conductivity_factor} {h["moistureDeficit"]}')
 k=20*conductivity_factor;exfil=10*conductivity_factor
 sections['LID_CONTROLS']=[
  'RG RG','RG SURFACE 150 0.1 0.15 1 0',f'RG SOIL 450 0.45 0.20 0.10 {k} 10 110',f'RG STORAGE 0 0.75 {exfil} 0',
  'PP PP','PP SURFACE 5 0 0.015 1 0',f'PP PAVEMENT 100 0.15 0 {100*conductivity_factor} 0',f'PP STORAGE 300 0.75 {exfil} 0',
  'GR GR','GR SURFACE 25 0.1 0.15 1 0',f'GR SOIL 150 0.45 0.20 0.10 {k} 10 110','GR DRAINMAT 25 0.5 0.1']
 sections['LID_USAGE']=[]
 for c in model['cells']:
  p=byid.get(c['id'])
  if p:
   t={'RAIN_GARDEN':'RG','PERMEABLE_PAVEMENT':'PP','GREEN_ROOF':'GR'}[p['facilityType']];a=float(p['areaM2'])
   sections['LID_USAGE'].append(f'{c["id"]} {t} 1 {a} {math.sqrt(a):.6f} {h["initialSaturationPercent"]} 100 0 * OUT 0')
 sections['TIMESERIES']=[]
 for i,depth in enumerate(rain['depthsMm']):
  # 구간 시작 시각으로 이동한 깊이 자료. 관측 시각 규약은 원본 메타데이터에 보존한다.
  t=start+timedelta(seconds=i*interval);sections['TIMESERIES'].append(f'RAIN_DATA {t:%m/%d/%Y} {t:%H:%M:%S} {depth}')
 sections['TIMESERIES'].append(f'RAIN_DATA {end:%m/%d/%Y} {end:%H:%M:%S} 0')
 sections['REPORT']=['INPUT NO','CONTROLS NO','SUBCATCHMENTS ALL','NODES ALL','LINKS ALL']
 return '\n\n'.join('['+k+']\n'+'\n'.join(v) for k,v in sections.items())+'\n'

def run(model,placements,directory,label,conductivity_factor=1.0,step_seconds=10):
 directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
 source=make_input(model,placements,conductivity_factor,step_seconds)
 inp=directory/f'{label}.inp';rpt=directory/f'{label}.rpt';out=directory/f'{label}.out';inp.write_text(source)
 lib=C.CDLL(str(library_path()));lib.swmm_getSavedValue.argtypes=[C.c_int,C.c_int,C.c_int];lib.swmm_getSavedValue.restype=C.c_double
 if lib.swmm_getVersion()!=52004:raise SimulationQualityError('ENGINE_VERSION_MISMATCH')
 def check(code):
  if code:raise SimulationQualityError('SWMM_ERROR_'+str(code))
 try:
  check(lib.swmm_open(os.fsencode(inp),os.fsencode(rpt),os.fsencode(out)))
  check(lib.swmm_start(1));elapsed=C.c_double()
  while True:
   check(lib.swmm_step(C.byref(elapsed)))
   if elapsed.value==0:break
  check(lib.swmm_end());check(lib.swmm_report())
  errors=[C.c_float() for _ in range(3)];check(lib.swmm_getMassBalErr(*(C.byref(e) for e in errors)))
  count=round((datetime.fromisoformat(model['rainfall']['end'])-datetime.fromisoformat(model['rainfall']['start'])).total_seconds()/60)
  series=[sum(lib.swmm_getSavedValue(205,c,p) for c in range(len(model['cells']))) for p in range(1,count+1)]
  warnings=lib.swmm_getWarnings()
 finally:lib.swmm_close()
 report=rpt.read_text();part=report.split('Runoff Quantity Continuity',1)[1].split('Continuity Error (%)',1)[0]
 area=sum(c['areaM2'] for c in model['cells'])
 def volume(name,optional=False):
  match=re.search(r'^\s*'+re.escape(name)+r'\s*\.+\s+([-\d.]+)\s+([-\d.]+)',part,re.M)
  if not match:
   if optional:return 0.0
   raise SimulationQualityError('REPORT_FIELD_MISSING')
  return float(match[2])*area/1000
 result={'surfaceRunoffM3':volume('Surface Runoff'),'lidDrainageM3':volume('LID Drainage',True),'finalStorageM3':volume('Final Storage'),'initialStorageM3':volume('Initial LID Storage',True),
  'infiltrationM3':volume('Infiltration Loss'),'evaporationM3':volume('Evaporation Loss'),'precipitationM3':volume('Total Precipitation'),
  'runoffContinuityPercent':errors[0].value,'routingContinuityPercent':None,'routingStatus':'NOT_APPLICABLE_NO_CONVEYANCE_NETWORK','peakM3s':max(series,default=0),'seriesM3s':series,'warnings':warnings}
 result['runoffM3']=result['surfaceRunoffM3']+result['lidDrainageM3']
 result['accountedDischargeM3']=result['runoffM3']+result['finalStorageM3']-result['initialStorageM3']
 result['seriesIntegralM3']=sum(series)*60
 for k,v in result.items():
  if isinstance(v,(int,float)) and not math.isfinite(v):raise SimulationQualityError('NON_FINITE_RESULT')
 if any(not math.isfinite(v) or v<0 for v in series) or abs(errors[0].value)>1 or warnings:raise SimulationQualityError('NUMERICAL_QUALITY_FAILED')
 if abs(result['seriesIntegralM3']-result['runoffM3'])>max(.1,result['runoffM3']*.03):raise SimulationQualityError('SERIES_VOLUME_MISMATCH')
 return result

def score(baseline,strategy):
 if baseline['accountedDischargeM3']<=1e-6:raise SimulationQualityError('BASELINE_TOO_SMALL')
 return round(100*(baseline['accountedDischargeM3']-strategy['accountedDischargeM3'])/baseline['accountedDischargeM3'],8)

def experiment(model,placements,directory):
 directory=Path(directory);baseline=run(model,[],directory,'baseline');strategy=run(model,placements,directory,'strategy')
 # 이 범위는 확률적 신뢰구간이 아니라 투수계수 가정에 대한 시나리오 비교다.
 sensitivity=[]
 for name,factor in [('low',.5),('high',1.5)]:
  s=run(model,placements,directory,name,conductivity_factor=factor);sensitivity.append({'conductivityFactor':factor,'score':score(baseline,s),'runoffM3':s['runoffM3']})
 (directory/'model.json').write_text(json.dumps(model,ensure_ascii=False,indent=2)+'\n')
 (directory/'placements.json').write_text(json.dumps(placements,ensure_ascii=False,indent=2)+'\n')
 result={'validationLevel':'EXPLORATORY','official':False,'scoreRule':model['scoreRule'],'score':score(baseline,strategy),'baseline':baseline,'strategy':strategy,'sensitivity':sensitivity,'assumptions':model['assumptions'],
  'engine':{'version':'5.2.4','revision':REVISION,'binarySha256':hashlib.sha256(library_path().read_bytes()).hexdigest(),'generatorSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'platform':platform.platform()},'reportPrecision':'보고서 깊이 0.001 mm; 시계열은 1분 보고시각 보간 유량; 적분은 품질 대조용 근사'}
 (directory/'builder.py').write_bytes(Path(__file__).read_bytes())
 (directory/'result.json').write_text(json.dumps(result,ensure_ascii=False,allow_nan=False)+'\n')
 manifest={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(directory.iterdir()) if p.is_file()}
 (directory/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
 return result
