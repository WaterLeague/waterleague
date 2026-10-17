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
assert model['currency'] == 'KRW' and model['costModel']['evidence'] == 'PUBLIC_PLAN_REFERENCE_SITE_TRANSFER_UNVERIFIED'
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

reference=json.loads((root / 'data/costs/lid-reference.json').read_text())
assert model['unitCosts']==reference['unitCosts'] and model['costModel']==reference['costModel']
for row in reference['sourceRows']:
 assert row['thousandKrwPerM2']*1000==model['unitCosts'][row['facility']]
 assert row['thousandKrwPerM2']*row['sourceAreaM2']==row['sourceTotalThousandKrw']

import sys
sys.path.insert(0, str(root/'simulation'))
from waterleague_sim.model_catalog import read_catalog
models=read_catalog(root/'data/models')
assert (root/'data/models/catalog.json').read_bytes()==(root/'backend/src/main/resources/models/catalog.json').read_bytes()
for entry in json.loads((root/'data/models/catalog.json').read_text())['models']:
 data=models[entry['sha256']]
 assert data==(root/'backend/src/main/resources/models'/entry['file']).read_bytes()
 item=json.loads(data); rain=item['rainfall']
 assert item['unitCosts']==model['unitCosts']
 if 'mapId' not in item:
  assert item['cells']==model['cells']
 else:
  assert item['mapId']=='seongsu-ngii-2025-v2'
  assert item['mapSnapshotHash']==hashlib.sha256((root/'frontend/public/data/seongsu-ngii-v2.json').read_bytes()).hexdigest()
  assert item['candidateSnapshotHash']==hashlib.sha256((root/'data/derived/seongsu-topography-candidates-v2.json').read_bytes()).hexdigest()
  assert item['geometrySourceHash']==hashlib.sha256((root/'data/manifests/seongsu-topography-sources.json').read_bytes()).hexdigest()
  assert item['geometryModelGeneratorSha256']==hashlib.sha256((root/'scripts/prepare_topography_models.py').read_bytes()).hexdigest()
 assert item['generatorSha256']==model['generatorSha256']
 assert rain['transformSha256']==model['rainfall']['transformSha256']
 assert len(rain['depthsMm'])>60 and all(x>=0 for x in rain['depthsMm'])
 assert sum(Decimal(str(x)) for x in rain['depthsMm'])==Decimal(str(rain['totalDepthMm']))
 assert (datetime.fromisoformat(rain['end'])-datetime.fromisoformat(rain['start'])).total_seconds()==len(rain['depthsMm'])*60
 if rain.get('sourceManifest'):
  assert rain['sourceHash']==json.loads((root/'data/manifests'/rain['sourceManifest']).read_text())['sha256']
  assert rain==json.loads((root/'data/derived/rainfall'/f"{rain['id']}.json").read_text())
print(f'모델 카탈로그 {len(models)}개·서버 원문·파생 강우 계보 검증 통과')
