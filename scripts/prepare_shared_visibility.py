"""공동 후보 원문에서 지도 표시용 건물 식별자 색인 생성."""
import gzip,hashlib,json
from pathlib import Path
root=Path(__file__).resolve().parents[1]
folder=root/'backend/src/main/resources/shared-sites'
source=(folder/'catalog.json').read_bytes();manifest=json.loads(source)
models={e['sha256']:e['file'] for e in json.loads((root/'data/models/catalog.json').read_text())['models']}
identifiers=set(); legacy_sources={}
for entry in manifest['entries']:
 raw=gzip.decompress((folder/entry['file']).read_bytes())
 assert hashlib.sha256(raw).hexdigest()==entry['sha256']
 snapshot=json.loads(raw)
 legacy=json.loads((root/'data/models'/models[snapshot['baseModelHash']]).read_text())
 for cell in legacy['cells']:
  if cell['kind']=='ROOF':legacy_sources[entry['districtId']+':'+cell['id']]=cell.get('sourceIds') or [cell['buildingId']]
 for cell in snapshot['cells']+legacy['cells']:
  if cell['kind']=='ROOF':identifiers.update(cell.get('sourceIds') or [cell['buildingId']])
value={'schemaVersion':1,'catalogSha256':hashlib.sha256(source).hexdigest(),'roofSourceIds':sorted(identifiers),'legacySiteSources':legacy_sources}
raw=(json.dumps(value,ensure_ascii=False,separators=(',',':'))+'\n').encode()
path=root/'frontend/public/data/seoul-site-eligibility-v1.json'
if path.exists():assert path.read_bytes()==raw
else:path.write_bytes(raw)
print(len(identifiers),'건물 색인',len(raw),'bytes',hashlib.sha256(raw).hexdigest())
