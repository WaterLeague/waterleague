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
    from .admission import archive_native as archive
    archive(request.get('publicAssetPolicy'), path)
    from .costing.snapshot import archive as archive_cost
    cost_record = archive_cost(request, model, request['placement'], path)
    if model.get('initializationPolicy') is not None:
        from .engine.initialization import prepend
        raw = (path/'antecedent.json').read_bytes()
        if digest(raw) != request.get('antecedentSha256'):
            raise ValueError('LIVE_ANTECEDENT_HASH_INVALID')
        model, evaporation = prepend(model, evaporation, json.loads(raw))
    from .weekly import RULE, SECOND_RULE
    rule = request.get('weeklyRuleVersion', RULE)
    if rule not in (RULE, SECOND_RULE) or (rule == RULE and 'installedAt' in request):
        raise ValueError('LIVE_WEEKLY_POLICY_INVALID')
    if rule == SECOND_RULE and (not request.get('installedAt')
            or request.get('installationClock') != 'SERVER_SECOND_RESOLUTION_V1'):
        raise ValueError('LIVE_INSTALLATION_TIME_INVALID')
    result = experiment(model, request['placement'], path, evaporation,
                        installed_at=request['installedAt'] if rule == SECOND_RULE else None)
    from .engine.direct_surface_contract import archive as archive_contract
    archive_contract(model, request['placement'], result, path, cost_record)


if __name__ == '__main__':
    main()
