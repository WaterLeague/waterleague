"""고정 가격 버전만 허용하고 이전 설치의 원가를 현재 가격으로 바꾸지 않음."""
from copy import deepcopy
from functools import lru_cache
import hashlib
import json
from pathlib import Path

from .snapshot import CostEvidenceError

PATH = Path(__file__).resolve().parents[3]/'backend/src/main/resources/facilities/game-prices-202608-v1.json'
SHA256 = '00b489edc185338156d660e16aca57bd3890f1314110c4db6b6e191044f22cb3'


@lru_cache(maxsize=1)
def catalog():
    raw = PATH.read_bytes()
    if hashlib.sha256(raw).hexdigest() != SHA256:
        raise CostEvidenceError()
    return json.loads(raw)


def apply(value, version=None):
    data = catalog()
    sha = data['currentCostSourceSha256'] if version is None else version
    original = data['versions'].get(value.get('costSourceSha256'))
    selected = data['versions'].get(sha)
    if (original is None or selected is None
            or any(value.get(k) != original[k] for k in ('unitCosts', 'costModel'))):
        raise CostEvidenceError()
    return deepcopy(value) | deepcopy(selected) | {'costSourceSha256': sha}


def recorded_version(raw, sha):
    if raw is None and sha is None:
        return catalog()['previousCostSourceSha256']
    try:
        if (not isinstance(raw, str) or len(raw.encode()) > 65536
                or hashlib.sha256(raw.encode()).hexdigest() != sha):
            raise CostEvidenceError()
        version = json.loads(raw)['costSourceSha256']
        if version not in catalog()['versions']:
            raise CostEvidenceError()
        return version
    except (TypeError, KeyError, ValueError):
        raise CostEvidenceError() from None
