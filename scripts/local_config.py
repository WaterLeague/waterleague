"""공통 로컬 설정. 값 출력·셸 평가 없이 환경변수 우선 적용."""
from pathlib import Path
import os
ROOT=Path(__file__).resolve().parents[1]
def load():
 p=ROOT/'.env.local'
 if p.exists():
  for line in p.read_text().splitlines():
   if not line.strip() or line.lstrip().startswith('#') or '=' not in line:continue
   key,value=line.split('=',1)
   if key.strip().replace('_','').isalnum():os.environ.setdefault(key.strip(),value.strip())
