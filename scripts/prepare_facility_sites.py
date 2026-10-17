"""기존 후보 형상을 보존하고 공개 시설 제원·선행 기상 초기화 계약 연결."""
import gzip
import hashlib
import json
import sys
from pathlib import Path
from local_config import ROOT
from prepare_shared_site_constraints import DIRECTORY, save
sys.path.insert(0, str(ROOT/'simulation'))
from waterleague_sim.engine.facilities import design_set
from waterleague_sim.engine.initialization import METHOD, MINUTES


def encode(value):
    return (json.dumps(value, ensure_ascii=False, separators=(',',':'), allow_nan=False)+'\n').encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    prior = (DIRECTORY/'catalog-v4.json').read_bytes()
    if sha(prior) != 'f1f8d5f366cf47fff86319b27669bfb8e4a1fd3912d701b70b4b6e280e6fa66f':
        raise ValueError('이전 후보 목록 해시 오류')
    policy = json.loads((ROOT/'backend/src/main/resources/budget/seoul-2026.json').read_text())
    entries = []
    for entry in json.loads(prior)['entries']:
        raw = (DIRECTORY/entry['file']).read_bytes()
        if sha(raw) != entry['gzipSha256']:
            raise ValueError('이전 후보 압축 해시 오류')
        raw = gzip.decompress(raw)
        if sha(raw) != entry['sha256']:
            raise ValueError('이전 후보 원문 해시 오류')
        value = json.loads(raw)
        value.update({'schemaVersion': 5, 'previousSnapshotSha256': entry['sha256'],
            'constraintVersion': 'PUBLIC_FACILITY_WEATHER_V5', 'facilityDesignSet': design_set(),
            'initializationPolicy': {'method': METHOD, 'warmupMinutes': MINUTES},
            'budget': policy['personalLimitKrw'], 'budgetPolicy': policy})
        value['limitations'] = [s for s in value['limitations'] if not s.startswith('시설 두께')]
        value['limitations'] += ['시설 제원은 EPA 공개 범위의 설계값, 초기 수분은 선행 관측의 연속 계산값이며 현장 실측 아님']
        raw = encode(value)
        compressed = gzip.compress(raw, mtime=0)
        name = entry['districtId']+'-v5.json.gz'
        save(DIRECTORY/name, compressed)
        entries.append(entry | {'file': name, 'sha256': sha(raw), 'gzipSha256': sha(compressed), 'bytes': len(raw)})
    value = {'schemaVersion': 5, 'previousCatalogSha256': sha(prior), 'facilityDesignSet': design_set(),
        'generatorSha256': sha(Path(__file__).read_bytes()), 'entries': entries}
    raw = encode(value)
    save(DIRECTORY/'catalog-v5.json', raw)
    save(ROOT/'data/manifests/shared-sites-v5.json', raw)
    print('catalog', sha(raw), flush=True)


if __name__ == '__main__':
    main()
