"""기존 형상·재료를 보존하고 빗물정원의 하부 침투 입력을 새 후보 버전에 연결."""
import gzip
import json
import sys
from pathlib import Path

from local_config import ROOT
from prepare_facility_sites import encode, sha
from prepare_shared_site_constraints import DIRECTORY, save

sys.path.insert(0, str(ROOT/'simulation'))
from waterleague_sim.engine.facilities import native_soil_boundary
from waterleague_sim.model_catalog import read_catalog


def main():
    prior = (DIRECTORY/'catalog-v5.json').read_bytes()
    if sha(prior) != '450f016165b58477ba4fb09eb81aec08de93d6081cd367ddf9b906920d7c6e07':
        raise ValueError('이전 후보 목록 해시 오류')
    models = read_catalog(ROOT/'data/models')
    entries, counts = [], {}
    for entry in json.loads(prior)['entries']:
        packed = (DIRECTORY/entry['file']).read_bytes()
        raw = gzip.decompress(packed)
        if sha(packed) != entry['gzipSha256'] or sha(raw) != entry['sha256']:
            raise ValueError('이전 후보 원문 해시 오류')
        value = json.loads(raw)
        hydrology = json.loads(models[value['baseModelHash']])['hydrology']
        value.update(schemaVersion=6, previousSnapshotSha256=entry['sha256'],
                     constraintVersion='PUBLIC_NATIVE_SOIL_BOUNDARY_V6')
        for cell in value['cells']:
            if 'RAIN_GARDEN' not in cell['allowedTypes']:
                continue
            boundary = native_soil_boundary(cell, hydrology)
            cell['physicalInputs']['rainGardenBoundary'] = boundary
            counts[boundary['basis']] = counts.get(boundary['basis'], 0)+1
        value['limitations'] += ['빗물정원 하부는 차수막 없는 설계 조건; 실제 차수막·지하수·도시 다짐 상태 미확인']
        raw = encode(value)
        packed = gzip.compress(raw, mtime=0)
        name = entry['districtId']+'-v6.json.gz'
        save(DIRECTORY/name, packed)
        entries.append(entry | {'file': name, 'sha256': sha(raw), 'gzipSha256': sha(packed), 'bytes': len(raw)})
    raw = encode({'schemaVersion': 6, 'previousCatalogSha256': sha(prior),
                  'generatorSha256': sha(Path(__file__).read_bytes()),
                  'boundaryImplementationSha256': sha((ROOT/'simulation/waterleague_sim/engine/facilities.py').read_bytes()),
                  'boundaryCounts': counts, 'entries': entries})
    save(DIRECTORY/'catalog-v6.json', raw)
    save(ROOT/'data/manifests/shared-sites-v6.json', raw)
    print('catalog', sha(raw), counts, flush=True)


if __name__ == '__main__':
    main()
