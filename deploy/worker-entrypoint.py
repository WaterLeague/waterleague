"""기상 API 키를 이미지·컨테이너 설정에 남기지 않고 워커 프로세스에 전달."""
import os
from pathlib import Path
import runpy

runpy.run_path('/app/deploy/reconcile_weekly.py', run_name='__main__')
key = Path('/run/secrets/kma-api-key').read_text().strip()
if not key:
    raise SystemExit('KMA_SECRET_MISSING')
os.environ['KMA_API_KEY'] = key
runpy.run_module('waterleague_sim.worker', run_name='__main__')
