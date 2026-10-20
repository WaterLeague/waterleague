"""원형 지붕에 문헌 이용조 설계를 결속하며 원본 공간 파일을 보존."""
from copy import deepcopy
from functools import lru_cache
import hashlib
import json

from ..engine.swmm import ROOT, SimulationQualityError

PATH = ROOT / 'backend/src/main/resources/facilities/cistern-game-v1.json'
SHA256 = '20da4bc15546b77aa680d07d61bc1d95a0f0c7aae95667d6c46fa080c2c270f3'
TYPE = 'RAINWATER_CISTERN'


@lru_cache(maxsize=1)
def rules():
    raw = PATH.read_bytes()
    if hashlib.sha256(raw).hexdigest() != SHA256:
        raise SimulationQualityError('CISTERN_GAME_RULES_INVALID')
    return json.loads(raw)


def metadata(value):
    result = deepcopy(value)
    rule = rules()
    result['facilityDesignSet'] = deepcopy(rule['facilityDesignSet'])
    result['unitCosts'][TYPE] = rule['cost']['unitCost']
    result['costModel']['facilities'][TYPE] = deepcopy(rule['cost'])
    result['costSourceSha256'] = hashlib.sha256(
        (value['costSourceSha256'] + ':' + SHA256).encode()).hexdigest()
    result['cisternGameSha256'] = SHA256
    result['limitations'] += rule['limitations']
    return result


def cell(value):
    if value.get('kind') == 'ROOF' and 'GREEN_ROOF' in value.get('allowedTypes', []):
        value = deepcopy(value)
        if TYPE not in value['allowedTypes']:
            value['allowedTypes'].append(TYPE)
    return value
