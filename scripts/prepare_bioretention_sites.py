"""공개 토성 후보의 침투형 생물저류 설계·비용·점유 경계를 새 버전으로 결속."""
import copy
import gzip
import json
import sys
from pathlib import Path
from local_config import ROOT
from prepare_facility_sites import encode, sha
from prepare_shared_site_constraints import DIRECTORY, save

sys.path.insert(0, str(ROOT/'simulation'))
from waterleague_sim.engine.facilities import bioretention_boundary, design_set


def main():
    prior = (DIRECTORY/'catalog-v6.json').read_bytes()
    if sha(prior) != '18a22093b2541ab05ed3fdee6a394a998bbfd5d092c6105cf787702f99bdf501':
        raise ValueError('이전 후보 목록 해시 오류')
    costs_raw = (ROOT/'data/costs/lid-reference-v3.json').read_bytes()
    if sha(costs_raw) != '7c5f961af6d6d29b29c3f9ea5b6df460ccca44003e37191683a1b0bb33b480f8':
        raise ValueError('공개 참고 원가 해시 오류')
    costs = json.loads(costs_raw)
    entries, counts, mapping = [], {}, {}
    for entry in json.loads(prior)['entries']:
        packed = (DIRECTORY/entry['file']).read_bytes()
        raw = gzip.decompress(packed)
        if sha(packed) != entry['gzipSha256'] or sha(raw) != entry['sha256']:
            raise ValueError('이전 후보 원문 해시 오류')
        value = json.loads(raw)
        before = copy.deepcopy(value['cells'])
        value.update(schemaVersion=7, previousSnapshotSha256=entry['sha256'],
                     constraintVersion='PUBLIC_BIORETENTION_DIRECT_RAIN_V7',
                     facilityDesignSet=design_set(2), costModel=costs,
                     costSourceSha256=sha(costs_raw),
                     unitCosts={key: row['unitCost'] for key, row in costs['facilities'].items()})
        count = 0
        for cell in value['cells']:
            if cell['kind'] != 'GROUND' or cell['physicalInputs'].get('soilStatus') != 'TEXTURE_CLASS_LITERATURE_ESTIMATE':
                continue
            cell['allowedTypes'].append('BIORETENTION')
            cell['physicalInputs']['bioretentionBoundary'] = bioretention_boundary(cell)
            count += 1
        # 설치 위치와 기존 3종 입력이 바뀌면 기존 점유 판정을 재사용하지 않는다.
        for old, new in zip(before, value['cells'], strict=True):
            restored = copy.deepcopy(new)
            restored['allowedTypes'] = [t for t in restored['allowedTypes'] if t != 'BIORETENTION']
            restored['physicalInputs'].pop('bioretentionBoundary', None)
            if old != restored:
                raise ValueError('기존 후보 형상·입력 변경')
        value['limitations'] += ['생물저류는 공개 토성에 근거한 비차수·무배수관 직접 강우 설계; 지하수·지장물·현장 시공 적합성 미확인']
        data = encode(value)
        compressed = gzip.compress(data, mtime=0)
        name = entry['districtId']+'-v7.json.gz'
        save(DIRECTORY/name, compressed)
        entries.append(entry | {'file': name, 'sha256': sha(data), 'gzipSha256': sha(compressed),
                                'bytes': len(data), 'bioretentionCount': count})
        counts[entry['districtId']] = count
        mapping[entry['districtId']] = (entry['sha256'], sha(data))
    raw = encode({'schemaVersion': 7, 'previousCatalogSha256': sha(prior),
                  'generatorSha256': sha(Path(__file__).read_bytes()),
                  'facilityDesignSet': design_set(2), 'costSourceSha256': sha(costs_raw),
                  'bioretentionCounts': counts, 'entries': entries})
    save(DIRECTORY/'catalog-v7.json', raw)
    save(ROOT/'data/manifests/shared-sites-v7.json', raw)
    policy_path = ROOT/'backend/src/main/resources/infrastructure/seoul-basin-footprints-20261018-v1.json'
    policy_raw = policy_path.read_bytes()
    if sha(policy_raw) != '65faea2a057d5aeb2a05b5ca2d09b2b962aa3888cfd615fb898119006cf7ec4c':
        raise ValueError('이전 공개 점유 정책 해시 오류')
    policy = json.loads(policy_raw)
    policy.update(version='seoul-basin-footprints-20261018-v2', previousPolicySha256=sha(policy_raw), siteCatalogSha256=sha(raw))
    for row in policy['exclusions']:
        old, new = mapping[row['districtId']]
        if row['siteModelHash'] != old:
            raise ValueError('기존 점유 경계 결속 오류')
        row['siteModelHash'] = new
    policy_raw = encode(policy)
    save(policy_path.with_name('seoul-basin-footprints-20261018-v2.json'), policy_raw)
    print('catalog', sha(raw), 'eligible', sum(counts.values()), 'policy', sha(policy_raw), flush=True)


if __name__ == '__main__':
    main()
