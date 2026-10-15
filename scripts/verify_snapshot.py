"""커밋된 자료·변환 코드와 출처 manifest의 연결 검증."""
from pathlib import Path
import hashlib
import json
import re

root=Path(__file__).resolve().parents[1]
manifest=json.loads((root/'data/manifests/public-data-audit.json').read_text())
snapshot=root/'frontend/public/data/seongsu.json'
assert hashlib.sha256(snapshot.read_bytes()).hexdigest()==manifest['map']['derivedHash'], '파생 자료 해시 불일치'
assert hashlib.sha256((root/'scripts/prepare_public_data.py').read_bytes()).hexdigest()==manifest['map']['transformSha256'], '변환 코드 해시 불일치'
data=json.loads(snapshot.read_text())
assert data['sourceHash']==manifest['map']['sourceHash'], '원본 계보 불일치'
assert not data['officialEvaluationAvailable'] and data['validationLevel']=='DRAFT', '미승인 자료 상태 오류'
assert len([f for f in data['features'] if f['kind']=='building'])==manifest['map']['buildings'], '형상 수 불일치'
for path in [root/'README.md',* (root/'docs').rglob('*.md')]:
    for target in re.findall(r'\]\(([^)]+)\)',path.read_text()):
        if not target.startswith(('http://','https://','#')):
            assert (path.parent/target.split('#')[0]).exists(), f'문서 링크 오류: {path.name}: {target}'
print('자료 계보·상태·문서 링크 검증 통과')
