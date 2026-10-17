"""배포된 모델 목록의 경로·원문 해시 검증."""
from pathlib import Path
import hashlib
import json
import re


def read_catalog(directory: Path):
    root = directory.resolve()
    document = json.loads((root/'catalog.json').read_text())
    if document.get('schemaVersion') != 1 or not 1 <= len(document.get('models', [])) <= 256:
        raise ValueError('모델 카탈로그 형식 오류')
    models = {}
    ids = set()
    files = set()
    for entry in document['models']:
        name, expected, identity = entry['file'], entry['sha256'], entry['id']
        if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,100}\.json', name) or name == 'catalog.json':
            raise ValueError('모델 경로 오류')
        if not re.fullmatch(r'[a-f0-9]{64}', expected) or expected in models or identity in ids or name in files:
            raise ValueError('모델 식별자 오류')
        path = root/name
        if path.is_symlink() or path.stat().st_size > 2*1024*1024:
            raise ValueError('모델 파일 크기·링크 오류')
        source = path.read_bytes()
        if hashlib.sha256(source).hexdigest() != expected:
            raise ValueError('모델 해시 불일치')
        model = json.loads(source)
        if model['id'] != identity or not model.get('simulationAvailable') or model.get('officialEvaluationAvailable') or model.get('validationLevel') != 'EXPLORATORY':
            raise ValueError('모델 등록 계약 불일치')
        ids.add(identity)
        files.add(name)
        models[expected] = source
    if document['defaultModelHash'] not in models:
        raise ValueError('기본 모델 누락')
    return models
