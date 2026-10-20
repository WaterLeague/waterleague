"""위치별 안전 조건의 결측 보존과 탐색 배치 제약."""
import copy
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

POLICY_FILE = Path(__file__).resolve().parents[3] / 'backend/src/main/resources/facilities/site-suitability-v1.json'
POLICY_RAW = POLICY_FILE.read_bytes()
POLICY = json.loads(POLICY_RAW)
POLICY_SHA256 = hashlib.sha256(POLICY_RAW).hexdigest()


class SiteSuitabilityError(ValueError):
    pass


def _status(value):
    if not isinstance(value, str) or value not in POLICY['priority']:
        raise SiteSuitabilityError('SITE_SUITABILITY_INVALID')
    return value


def _restrictions(cell):
    return [_status(cell[key]) for key in ('siteEligibility', 'constructionEligibility') if key in cell]


def assess(cell):
    kind = cell.get('kind')
    if kind not in ('ROOF', 'GROUND'):
        raise SiteSuitabilityError('SITE_SUITABILITY_INVALID')
    definitions = [item['id'] for item in POLICY['conditions'] if kind in item['kinds']]
    supplied = cell.get('siteConditions', {})
    if not isinstance(supplied, dict) or set(supplied) - set(definitions):
        raise SiteSuitabilityError('SITE_SUITABILITY_INVALID')
    checks = []
    for key in definitions:
        row = supplied.get(key)
        if row is None and key not in supplied:
            checks.append({'id': key, 'status': 'UNKNOWN', 'reason': POLICY['unknownReason'], 'evidence': None})
            continue
        if not isinstance(row, dict) or set(row) != {'status', 'reason', 'evidence'}:
            raise SiteSuitabilityError('SITE_SUITABILITY_INVALID')
        state, reason, evidence = _status(row['status']), row['reason'], row['evidence']
        if not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 500:
            raise SiteSuitabilityError('SITE_SUITABILITY_INVALID')
        if evidence is not None:
            if not isinstance(evidence, dict) or set(evidence) != {'title', 'url', 'sha256', 'reference'}:
                raise SiteSuitabilityError('SITE_SUITABILITY_INVALID')
            if any(not isinstance(evidence[k], str) or not 1 <= len(evidence[k].strip()) <= limit
                   for k, limit in (('title', 300), ('url', 2000), ('sha256', 64), ('reference', 500))):
                raise SiteSuitabilityError('SITE_SUITABILITY_INVALID')
            try:
                link = urlsplit(evidence['url'])
                if (link.scheme != 'https' or not link.hostname or link.username is not None
                        or link.password is not None or re.search(r'\s', evidence['url'])
                        or not re.fullmatch('[a-f0-9]{64}', evidence['sha256'])):
                    raise ValueError()
            except ValueError:
                raise SiteSuitabilityError('SITE_SUITABILITY_INVALID') from None
        elif state != 'UNKNOWN':
            raise SiteSuitabilityError('SITE_SUITABILITY_INVALID')
        checks.append({'id': key, **copy.deepcopy(row)})
    states = [row['status'] for row in checks]
    # 기존 집계의 금지·조건부는 유지하고, 허용 표기만으로 결측 세부 조건을 채우지 않는다.
    states += [state for state in _restrictions(cell) if state in ('PROHIBITED', 'CONDITIONAL')]
    status = next(state for state in POLICY['priority'] if state in states)
    return {'version': POLICY['version'], 'policySha256': POLICY_SHA256,
            'status': status, 'explorationAllowed': status in POLICY['explorationAllowed'],
            'constructionApproved': False, 'checks': checks}


def require_explorable(cell):
    if cell.get('kind') in ('GROUND', 'ROOF'):
        report = assess(cell)
        if not report['explorationAllowed']:
            raise SiteSuitabilityError('SITE_SUITABILITY_RESTRICTED')
        return report
    # 별도 연구 모형에도 명시된 금지를 적용하며, 위치 종류 없는 조건표는 수용하지 않는다.
    if 'siteConditions' in cell:
        raise SiteSuitabilityError('SITE_SUITABILITY_INVALID')
    if any(state in ('PROHIBITED', 'CONDITIONAL') for state in _restrictions(cell)):
        raise SiteSuitabilityError('SITE_SUITABILITY_RESTRICTED')
    return None
