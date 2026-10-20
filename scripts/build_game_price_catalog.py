"""원형 공간 자료와 분리한 이전·현재 설치 단가 허용 목록 생성."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT/'backend/src/main/resources/facilities/game-prices-202608-v1.json'


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def build():
    base_raw = (ROOT/'data/costs/lid-reference-v5.json').read_bytes()
    cistern_raw = (ROOT/'backend/src/main/resources/facilities/cistern-game-v1.json').read_bytes()
    estimate_raw = (ROOT/'data/costs/lid-index-estimates-202608-v2.json').read_bytes()
    original = json.loads(base_raw)
    before_cistern = deepcopy(original)
    original['facilities']['RAINWATER_CISTERN'] = json.loads(cistern_raw)['cost']
    previous = digest((digest(base_raw)+':'+digest(cistern_raw)).encode())
    if previous != '6c5f0e9dc9034189da2ddbc5de56a5382f364af41edb4f48ffde2a050c8b346c':
        raise ValueError('ORIGINAL_PRICE_VERSION_CHANGED')
    updated = deepcopy(original)
    updated.update(schemaVersion=7, previousSha256=previous)
    updated['facilities'].update(json.loads(estimate_raw)['facilities'])
    current = digest((previous+':'+digest(estimate_raw)).encode())
    def fields(model):
        return {'costModel': model, 'unitCosts': {k:v['unitCost'] for k,v in model['facilities'].items()}}
    return {'schemaVersion':1, 'id':'KICT_202608_GAME_PRICES_V1',
        'previousCostSourceSha256':previous, 'currentCostSourceSha256':current,
        'estimateSha256':digest(estimate_raw), 'generatorSha256':digest(Path(__file__).read_bytes()),
        'versions':{digest(base_raw):fields(before_cistern), previous:fields(original), current:fields(updated)}}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    raw = (json.dumps(build(), ensure_ascii=False, sort_keys=True, indent=2)+'\n').encode()
    if args.check:
        if OUTPUT.read_bytes() != raw:
            raise SystemExit('가격 버전 허용 목록 불일치')
    else:
        OUTPUT.write_bytes(raw)
    print(digest(raw))
