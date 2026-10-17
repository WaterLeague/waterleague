"""공개 형상과 명시적 가정으로 탐색 모델 구성. 현장 설치 적합성 미보증."""
from pathlib import Path
import json,hashlib,math
from pyproj import Geod
from shapely.geometry import Polygon,box
ROOT=Path(__file__).resolve().parents[1]
snapshot=json.loads((ROOT/'frontend/public/data/seongsu.json').read_text())
buildings=[b for b in snapshot['features'] if b['kind']=='building']
geo=Geod(ellps='WGS84');cells=[]
for b in sorted(buildings,key=lambda b:b['displayAreaM2'],reverse=True)[:8]:
 lon,lat=zip(*b['geographicCoordinates']);area=round(abs(geo.polygon_area_perimeter(lon,lat)[0]),2)
 cells.append(dict(id='R'+str(len(cells)+1),name=b['name'] or f'옥상 후보 {len(cells)+1}',buildingId=b['id'],kind='ROOF',coordinates=b['coordinates'],center=b['center'],heightM=b['heightM'],areaM2=area,maxAreaM2=round(area*.6,2),allowedTypes=['GREEN_ROOF'],areaEvidence='OSM_WGS84_GEODESIC',eligibilityEvidence='ASSUMED_NOT_SITE_APPROVED'))
shapes=[Polygon(b['coordinates']) for b in buildings]
for x,y in [(-110,-85),(-90,90),(100,-65),(70,100),(-40,-110),(100,60),(-100,-20),(20,90),(-50,20),(50,-50)]:
 shape=box(x-5,y-5,x+5,y+5)
 if any(shape.intersects(p) for p in shapes):continue
 cells.append(dict(id='G'+str(len(cells)-7),name=f'지상 실험 구역 {len(cells)-7}',kind='GROUND',coordinates=list(shape.exterior.coords),center=[x,y],heightM=.12,areaM2=100,maxAreaM2=80,allowedTypes=['RAIN_GARDEN','PERMEABLE_PAVEMENT'],areaEvidence='ASSUMED_EXPERIMENTAL_PATCH',eligibilityEvidence='ASSUMED_LANDCOVER_NOT_SURVEYED'))
model=dict(id='seongsu-exploratory-v1',title='성수 빗물 설계 실험',validationLevel='EXPLORATORY',officialEvaluationAvailable=False,simulationAvailable=False,engine='EPA SWMM 5.2.4',engineRevision='7952ca837988b1c32f791812eccc9fd64547e093',budget=300000000,maxPlacements=len(cells),unitCosts={'RAIN_GARDEN':180000,'PERMEABLE_PAVEMENT':120000,'GREEN_ROOF':220000},geometrySourceHash=snapshot['sourceHash'],cells=cells,rainfall=None,assumptions=['관측소 강우를 모든 실험 단위에 동일 적용; 부지 대표성 미검증','선정한 표면 단위만 계산; 성수동 전체 유역·관망·침수 미모델링','불투수율 100%, 경사 1%, 유출 폭 면적 제곱근 가정','시설 제원·토양·초기 함수 상태·설치 가능성 가정; 현장 조사·보정 없음','실제 건물 경계와 실측 강우가 포함되어도 현장 예측 검증을 의미하지 않음'],hydrology={'imperviousPercent':100,'slopePercent':1,'nImpervious':.015,'depressionMm':1.5,'suctionMm':110,'conductivityMmH':10,'moistureDeficit':.25,'evaporationMmDay':0,'initialSaturationPercent':0},scoreRule='VOLUME_WITH_FINAL_STORAGE_V1',rainfallSource='기상청 분자료 활용신청 대기')
model['assumptions'].extend(['선정 표면의 잔여 불투수면 유출 전량을 해당 LID로 유입시키는 가정; 실제 유입 동선 미검증', '증발 0 가정·최종 잔여저류는 평가체적에 포함; 녹화지붕의 일시 저류·장기 증발편익을 점수로 산정하지 않음', '유량 시계열은 1분 보고시각 보간값이며 분 평균값이 아님; 실제 관망 합류 첨두·침수깊이 산정 불가'])
costs=json.loads((ROOT/'data/costs/lid-reference.json').read_text())
model.update({k:costs[k] for k in ('budget','budgetEvidence','unitCosts','costModel')})
model['currency']='KRW';model['costEvidence']=costs['costModel']['evidence']
p=ROOT/'data/models/seongsu-lab.json';p.parent.mkdir(exist_ok=True);p.write_text(json.dumps(model,ensure_ascii=False,indent=2)+'\n')
target=ROOT/'backend/src/main/resources/models/seongsu-lab.json';target.parent.mkdir(exist_ok=True);target.write_bytes(p.read_bytes())
print('실험 단위',len(cells),'공식 평가 비활성')
