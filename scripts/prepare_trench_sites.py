"""침투 트렌치의 공개 후보·고정 폭 설계·참고 원가·점유 경계 결속."""
import copy
import gzip
import json
import sys
from pathlib import Path
from local_config import ROOT
from prepare_facility_sites import encode, sha
from prepare_shared_site_constraints import DIRECTORY, save

sys.path.insert(0, str(ROOT/'simulation'))
from waterleague_sim.engine.facilities import design_set, trench_boundary
from trench_geometry import contained_design


def main():
    prior = (DIRECTORY/'catalog-v8.json').read_bytes()
    if sha(prior) != 'd58dbf9cf2d6b44342c8ca468d7d5d4f8d4145ef3946fd8d5789b8cacebab8d9':
        raise ValueError('이전 후보 목록 해시 오류')
    costs_raw = (ROOT/'data/costs/lid-reference-v5.json').read_bytes()
    if sha(costs_raw) != '50f6e00757ecba3ed77a811b0fd9d03f72b800c0c47712093bf1adda99421036':
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
        value.update(schemaVersion=9, previousSnapshotSha256=entry['sha256'],
                     constraintVersion='PUBLIC_TRENCH_DIRECT_RAIN_V9',
                     facilityDesignSet=design_set(4), costModel=costs,
                     costSourceSha256=sha(costs_raw),
                     unitCosts={key: row['unitCost'] for key, row in costs['facilities'].items()})
        count = 0
        for cell in value['cells']:
            design = contained_design(cell)
            if design is None:
                continue
            cell['allowedTypes'].append('INFILTRATION_TRENCH')
            cell['physicalInputs']['trenchDesign'] = design
            cell['physicalInputs']['trenchBoundary'] = trench_boundary(cell)
            count += 1
        # 설치 위치와 기존 5종 입력이 바뀌면 기존 점유 판정을 재사용하지 않는다.
        for old, new in zip(before, value['cells'], strict=True):
            restored = copy.deepcopy(new)
            restored['allowedTypes'] = [t for t in restored['allowedTypes'] if t != 'INFILTRATION_TRENCH']
            restored['physicalInputs'].pop('trenchDesign', None)
            restored['physicalInputs'].pop('trenchBoundary', None)
            if old != restored:
                raise ValueError('기존 후보 형상·입력 변경')
        value['limitations'] += ['침투 트렌치는 공개 도형 내부 폭 1m 직선 설계; 문헌 토성 추정이며 실제 굴착·출구·시공 적합성 미확인']
        data = encode(value)
        compressed = gzip.compress(data, mtime=0)
        name = entry['districtId']+'-v9.json.gz'
        save(DIRECTORY/name, compressed)
        entries.append(entry | {'file': name, 'sha256': sha(data), 'gzipSha256': sha(compressed),
                                'bytes': len(data), 'trenchCount': count})
        counts[entry['districtId']] = count
        mapping[entry['districtId']] = (entry['sha256'], sha(data))
    raw = encode({'schemaVersion': 9, 'previousCatalogSha256': sha(prior),
                  'generatorSha256': sha(Path(__file__).read_bytes()),
                  'sharedGeometryGeneratorSha256': sha(Path(__file__).with_name('straight_footprint.py').read_bytes()),
                  'geometryGeneratorSha256': sha(Path(__file__).with_name('trench_geometry.py').read_bytes()),
                  'facilityDesignSet': design_set(4), 'costSourceSha256': sha(costs_raw),
                  'trenchCounts': counts, 'entries': entries})
    save(DIRECTORY/'catalog-v9.json', raw)
    save(ROOT/'data/manifests/shared-sites-v9.json', raw)
    policy_path = ROOT/'backend/src/main/resources/infrastructure/seoul-basin-footprints-20261018-v3.json'
    policy_raw = policy_path.read_bytes()
    if sha(policy_raw) != '4937ca34cfeb59441ea80c539863f8359207e6ad27af7c227e600af523463d16':
        raise ValueError('이전 공개 점유 정책 해시 오류')
    policy = json.loads(policy_raw)
    policy.update(version='seoul-basin-footprints-20261018-v4', previousPolicySha256=sha(policy_raw), siteCatalogSha256=sha(raw))
    for row in policy['exclusions']:
        old, new = mapping[row['districtId']]
        if row['siteModelHash'] != old:
            raise ValueError('기존 점유 경계 결속 오류')
        row['siteModelHash'] = new
    policy_raw = encode(policy)
    save(policy_path.with_name('seoul-basin-footprints-20261018-v4.json'), policy_raw)
    print('catalog', sha(raw), 'eligible', sum(counts.values()), 'policy', sha(policy_raw), flush=True)


if __name__ == '__main__':
    main()
