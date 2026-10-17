"""공동 설치의 고정 입력만 받는 격리 연속 계산 프로세스."""
import json
import os
import resource
import sys
from pathlib import Path
from .engine.continuous import digest, engine_identity, experiment


def main():
    os.umask(0o077)
    resource.setrlimit(resource.RLIMIT_CPU, (75, 75))
    resource.setrlimit(resource.RLIMIT_FSIZE, (64*1024*1024, 64*1024*1024))
    if sys.platform.startswith('linux'):
        resource.setrlimit(resource.RLIMIT_AS, (1536*1024*1024, 1536*1024*1024))
    path = Path(sys.argv[1])
    request = json.loads((path/'request.json').read_text())
    source = (path/'model-source.json').read_bytes()
    forcing = (path/'forcing.json').read_bytes()
    if (request['modelSha256'] != digest(source) or request['forcingSha256'] != digest(forcing)
            or request['engine'] != engine_identity()):
        raise ValueError('LIVE_REQUEST_HASH_INVALID')
    model, evaporation = json.loads(source), json.loads(forcing).get('evaporation')
    if model.get('initializationPolicy') is not None:
        from .engine.initialization import prepend
        raw = (path/'antecedent.json').read_bytes()
        if digest(raw) != request.get('antecedentSha256'):
            raise ValueError('LIVE_ANTECEDENT_HASH_INVALID')
        model, evaporation = prepend(model, evaporation, json.loads(raw))
    experiment(model, request['placement'], path, evaporation)


if __name__ == '__main__':
    main()
