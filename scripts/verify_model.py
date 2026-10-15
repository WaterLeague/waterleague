"""원본 비밀값 없이 커밋된 실험 조건·파생자료·빌더의 계보 검증."""
from pathlib import Path
from datetime import datetime
from decimal import Decimal
import hashlib
import json

root = Path(__file__).resolve().parents[1]
source = root / 'data/models/seongsu-lab.json'
assert source.read_bytes() == (root / 'backend/src/main/resources/models/seongsu-lab.json').read_bytes()
model = json.loads(source.read_text())
assert model['validationLevel'] == 'EXPLORATORY' and not model['officialEvaluationAvailable']
assert model['currency'] == 'KRW' and model['costModel']['evidence'] == 'ASSUMED_UNVERIFIED'
assert model['generatorSha256'] == hashlib.sha256((root / 'simulation/waterleague_sim/engine/swmm.py').read_bytes()).hexdigest()
rain = json.loads((root / 'data/derived/kma-event.json').read_text())
assert rain == model['rainfall'] == json.loads((root / 'frontend/public/data/kma-event.json').read_text())
assert rain['transformSha256'] == hashlib.sha256((root / 'simulation/waterleague_sim/ingestion/kma.py').read_bytes()).hexdigest()
manifest = json.loads((root / 'data/manifests/kma-108-202407180500-202407182359.json').read_text())
assert rain['sourceHash'] == manifest['sha256']
assert all(x >= 0 for x in rain['depthsMm'])
assert sum(Decimal(str(x)) for x in rain['depthsMm']) == Decimal(str(rain['totalDepthMm']))
assert (datetime.fromisoformat(rain['end']) - datetime.fromisoformat(rain['start'])).total_seconds() == len(rain['depthsMm']) * rain['intervalSeconds']
assert len({c['id'] for c in model['cells']}) == len(model['cells'])
assert all(0 < c['maxAreaM2'] <= c['areaM2'] for c in model['cells'])
print('실험 모델·관측 강우·원화 비용 근거·엔진 빌더 계보 검증 통과')
