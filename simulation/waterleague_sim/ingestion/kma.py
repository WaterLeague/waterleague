"""AWS 일 누적 강우를 분당 깊이로 변환. 자정 경계는 추정하지 않고 거부."""
from datetime import datetime,timedelta,timezone
from decimal import Decimal
from .rainfall import RainInterval,require_complete,RainfallQualityError
KST=timezone(timedelta(hours=9))

def normalize(text):
 rows=[]
 for line in text.splitlines():
  if not line or line.startswith('#'):continue
  fields=line.split()
  if len(fields)!=18:raise RainfallQualityError('AWS 필드 수 오류')
  t=datetime.strptime(fields[0],'%Y%m%d%H%M').replace(tzinfo=KST)
  values=[Decimal(fields[i]) for i in (10,11,13)]
  if any(not v.is_finite() or v<0 for v in values):raise RainfallQualityError('결측·오류·음수 강우')
  rows.append((t,fields[1],*values))
 if len(rows)<61:raise RainfallQualityError('최소 61개 관측 필요')
 intervals=[]
 for previous,current in zip(rows,rows[1:]):
  a,b=previous[0],current[0]
  if a.date()!=b.date() or a.hour==0 and a.minute==0:raise RainfallQualityError('일 누적 초기화 경계')
  if b-a!=timedelta(minutes=1) or previous[1]!=current[1]:raise RainfallQualityError('시간 간격·관측소 오류')
  depth=current[4]-previous[4]
  intervals.append(RainInterval(current[1],a.astimezone(timezone.utc),b.astimezone(timezone.utc),depth,'BASIC_CHECKED',f'{current[1]}:{b.isoformat()}'))
 total=require_complete(intervals,intervals[0].start,intervals[-1].end,60,frozenset({'BASIC_CHECKED'}))
 for window,index in [(15,2),(60,3)]:
  for i in range(window,len(rows)):
   observed=sum(r.depth_mm for r in intervals[i-window:i])
   if abs(observed-rows[i][index])>Decimal('0.1'):raise RainfallQualityError('이동 누적 강우 불일치')
 return intervals,total
