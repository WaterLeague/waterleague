"""커밋된 구 전역 후보 원문·도형·기존 모델 참조 검사."""
import gzip
import hashlib
import json
from pathlib import Path
from shapely.geometry import Polygon
from shapely.strtree import STRtree
root=Path(__file__).resolve().parents[1]
folder=root/'backend/src/main/resources/shared-sites'
manifest=json.loads((folder/'catalog.json').read_text())
assert (folder/'catalog.json').read_bytes()==(root/'data/manifests/shared-sites-v1.json').read_bytes()
assert manifest['generatorSha256']==hashlib.sha256((root/'scripts/prepare_shared_sites.py').read_bytes()).hexdigest()
models={e['sha256'] for e in json.loads((root/'data/models/catalog.json').read_text())['models']}
count=325
for entry in manifest['entries']:
 packed=(folder/entry['file']).read_bytes(); raw=gzip.decompress(packed)
 assert hashlib.sha256(packed).hexdigest()==entry['gzipSha256']
 assert len(raw)==entry['bytes'] and hashlib.sha256(raw).hexdigest()==entry['sha256']
 doc=json.loads(raw); cells=doc['cells']
 assert doc['baseModelHash'] in models and doc['sourceSha256']==manifest['sourceSha256']
 assert len(cells)==entry['count']==len({c['id'] for c in cells})
 shapes=[]
 for c in cells:
  g=Polygon(c['coordinates']); shapes.append(g)
  assert g.is_valid and abs(g.area-c['areaM2'])<.01 and 0<c['maxAreaM2']<c['areaM2']
  assert c['sourceIds'] and c['siteEligibility']=='UNKNOWN' and len(c['id'])<=20
 tree=STRtree(shapes)
 for i,g in enumerate(shapes):
  for j in tree.query(g):
   if j>i: assert g.intersection(shapes[j]).area<.001
 count+=len(cells)
print('공동 후보',count,'곳 원문·도형·중첩·참조 검사 통과')

import subprocess,sys
subprocess.run([sys.executable,str(root/'scripts/prepare_shared_visibility.py')],check=True)
