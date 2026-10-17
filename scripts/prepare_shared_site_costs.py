"""공개 비용 근거를 신규 후보에 고정하고 이전 설치 입력 보존."""
import gzip
import json
from pathlib import Path
from prepare_shared_site_constraints import ROOT, DIRECTORY, encode, sha, save

def main():
    previous=(DIRECTORY/'catalog-v2.json').read_bytes()
    if sha(previous)!='009fcd085f476bbc96a41888646f284942cd69aae0b9405defcb2764a8d6d5ea':
        raise ValueError('이전 후보 목록 해시 오류')
    costs_raw=(ROOT/'data/costs/lid-reference-v2.json').read_bytes()
    costs=json.loads(costs_raw)
    policy=json.loads((ROOT/'backend/src/main/resources/budget/seoul-2026.json').read_text())
    entries=[]
    for entry in json.loads(previous)['entries']:
        raw=(DIRECTORY/entry['file']).read_bytes()
        decoded=gzip.decompress(raw)
        if sha(raw)!=entry['gzipSha256'] or sha(decoded)!=entry['sha256']:
            raise ValueError('이전 후보 해시 오류')
        model=json.loads(decoded)
        model.update({'schemaVersion':3,'previousSnapshotSha256':entry['sha256'],
            'costSourceSha256':sha(costs_raw),'costModel':costs,
            'budget':policy['limitKrw'],'budgetPolicy':policy,
            'unitCosts':{k:v['unitCost'] for k,v in costs['facilities'].items()}})
        data=encode(model);compressed=gzip.compress(data,mtime=0)
        name=entry['districtId']+'-v3.json.gz';save(DIRECTORY/name,compressed)
        entries.append(entry|{'file':name,'sha256':sha(data),'gzipSha256':sha(compressed),'bytes':len(data)})
    data=encode({'schemaVersion':3,'previousCatalogSha256':sha(previous),
        'generatorSha256':sha(Path(__file__).read_bytes()),'costSourceSha256':sha(costs_raw),'entries':entries})
    save(DIRECTORY/'catalog-v3.json',data);save(ROOT/'data/manifests/shared-sites-v3.json',data)
    print('catalog',sha(data))

if __name__=='__main__':main()
