"""공통 로컬 설정. 값 출력·셸 평가 없이 환경변수 우선 적용."""
from pathlib import Path
import os
ROOT=Path(__file__).resolve().parents[1]
def load():
 for p in (ROOT/'.env.local', ROOT/'.env'):
  if not p.exists():continue
  for line in p.read_text().splitlines():
   if not line.strip() or line.lstrip().startswith('#') or '=' not in line:continue
   key,value=line.split('=',1)
   value=value.strip()
   if len(value)>=2 and value[0]==value[-1] and value[0] in ('"',"'"):value=value[1:-1]
   if key.strip().replace('_','').isalnum():os.environ.setdefault(key.strip(),value)
