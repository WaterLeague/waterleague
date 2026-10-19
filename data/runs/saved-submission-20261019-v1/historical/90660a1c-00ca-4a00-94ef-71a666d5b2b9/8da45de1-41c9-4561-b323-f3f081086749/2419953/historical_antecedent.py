"""과거 재해의 선행 입력과 원문 무결성 검사·재현 묶음 포함."""
import gzip
import json
import re
from pathlib import Path
from .engine.continuous import ROOT, digest

CATALOG_SHA256 = '5dc164c212778a60a8add9cc1dfc828d471edd0d4347b50fb94df28b1fb56b3c'


def load(model_hash, directory):
    root = ROOT/'data/derived/antecedent'
    raw = (root/'catalog-v1.json').read_bytes()
    if digest(raw) != CATALOG_SHA256:
        raise ValueError('HISTORICAL_ANTECEDENT_CATALOG_INVALID')
    catalog = json.loads(raw)
    entries = [e for e in catalog['entries'] if model_hash in e['modelHashes']]
    if len(entries) != 1:
        raise ValueError('HISTORICAL_ANTECEDENT_BINDING_INVALID')
    entry, value = entries[0], {}
    directory.mkdir(parents=True, exist_ok=True)
    (directory/'antecedent-catalog.json').write_bytes(raw)
    generator=(root/'generator.py').read_bytes()
    if digest(generator)!=catalog['generatorSha256']:
        raise ValueError('HISTORICAL_ANTECEDENT_SOURCE_INVALID')
    (directory/'antecedent-generator.py').write_bytes(generator)
    (directory/'historical_antecedent.py').write_bytes(Path(__file__).read_bytes())
    for kind in ('rainfall', 'evaporation'):
        ref = entry[kind]
        if not re.fullmatch(r'seoul-\d{8}-(\d{1,5}-rain|pet)-v1.json.gz', ref['file']):
            raise ValueError('HISTORICAL_ANTECEDENT_SOURCE_INVALID')
        body = (root/ref['file']).read_bytes()
        if digest(body) != ref['sha256']:
            raise ValueError('HISTORICAL_ANTECEDENT_SOURCE_INVALID')
        value[kind] = json.loads(gzip.decompress(body))
        (directory/ref['file']).write_bytes(body)
        for source in value[kind]['sourceRequests']:
            if not re.fullmatch(r'data/raw/kma-disaster-pet-[a-f0-9]{24}.txt', source['rawFile']):
                raise ValueError('HISTORICAL_ANTECEDENT_SOURCE_INVALID')
            data = (ROOT/source['rawFile']).read_bytes()
            if digest(data) != source['sha256']:
                raise ValueError('HISTORICAL_ANTECEDENT_SOURCE_INVALID')
            (directory/('s'+source['sha256']+'.txt')).write_bytes(data)
    for module, sha in catalog['implementationHashes'].items():
        if not re.fullmatch(r'[a-f0-9]{64}',sha) or not re.fullmatch(r'(ingestion|engine)/[a-z_]+.py',module):
            raise ValueError('HISTORICAL_ANTECEDENT_SOURCE_INVALID')
        body=(root/'implementations'/(sha+'.py')).read_bytes()
        if digest(body)!=sha: raise ValueError('HISTORICAL_ANTECEDENT_SOURCE_INVALID')
        (directory/('antecedent-'+module.replace('/','-'))).write_bytes(body)
    return value
