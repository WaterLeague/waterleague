"""기상 API 키를 이미지·컨테이너 설정에 남기지 않고 워커 프로세스에 전달."""
import os
from pathlib import Path
import runpy

key = Path('/run/secrets/kma-api-key').read_text().strip()
if not key:
    raise SystemExit('KMA_SECRET_MISSING')
os.environ['KMA_API_KEY'] = key
backup = Path('/run/secrets/kma-api-key-backup')
if backup.exists():
    os.environ['KMA_API_KEY_BACKUP'] = backup.read_text().strip()
runpy.run_module('waterleague_sim.worker', run_name='__main__')
