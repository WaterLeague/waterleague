"""고정 공개 모형·원 입력 해시와 원자적 게시 저장소."""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import stat
import uuid

from waterleague_sim.engine.flood_errors import FloodModelError, require
from waterleague_sim.engine.swmm import ROOT

REGISTRY = ROOT/'backend/src/main/resources/surface/public-models-v1.json'
REGISTRY_SHA256 = 'e4d5625e18077516f2d00c69fb2c6644765e5075bd6f2823578c0f791cd59fe3'
CLASSIFICATION = 'PUBLIC_INPUT_UNCALIBRATED_CURRENT_BASELINE'
CITY_FILE = 'frontend/public/data/seoul-native-v1/city.json'
CITY_SHA256 = '67a8b80b7036590973b7db99053521333f9405e1076a7939bfe491c43296dd6c'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encode(value):
    return (json.dumps(value,ensure_ascii=False,sort_keys=True,allow_nan=False)+'\n').encode()


def decode(raw):
    def pairs(items):
        result={}
        for key,value in items:
            require(key not in result,'PUBLIC_SURFACE_DUPLICATE_FIELD')
            result[key]=value
        return result
    def reject(_):
        raise FloodModelError('PUBLIC_SURFACE_NONFINITE_JSON')
    try:
        return json.loads(raw,object_pairs_hook=pairs,parse_constant=reject)
    except (ValueError,UnicodeError):
        raise FloodModelError('PUBLIC_SURFACE_JSON_INVALID') from None


def safe_path(root, name):
    root=Path(root).absolute()
    relative=PurePosixPath(name)
    require(relative.parts and not relative.is_absolute() and '..' not in relative.parts,
            'PUBLIC_SURFACE_PATH_INVALID')
    path=root/relative
    require(path.resolve()==path and not any(p.is_symlink() for p in (path,*path.parents)),
            'PUBLIC_SURFACE_PATH_INVALID')
    return path


def read(path, *, maximum=32*1024**2, expected=None):
    path=Path(path).absolute()
    require(path.resolve()==path and not any(p.is_symlink() for p in (path,*path.parents)),
            'PUBLIC_SURFACE_PATH_INVALID')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    with os.fdopen(fd,'rb') as source:
        require(stat.S_ISREG(os.fstat(source.fileno()).st_mode),'PUBLIC_SURFACE_FILE_INVALID')
        raw=source.read(maximum+1)
    require(len(raw)<=maximum and (expected is None or sha(raw)==expected),
            'PUBLIC_SURFACE_HASH_OR_SIZE_MISMATCH')
    return raw


def city_source(root):
    try:
        raw = read(safe_path(root, CITY_FILE), maximum=8*1024**2, expected=CITY_SHA256)
    except OSError:
        raise FloodModelError('PUBLIC_SURFACE_MAP_UNAVAILABLE') from None
    city = decode(raw)
    require(isinstance(city, dict) and city.get('schemaVersion') == 2
            and city.get('id') == 'seoul-ngii-20260307'
            and city.get('coordinateSystem') == 'EPSG:5186'
            and city.get('originProjected') == [198128., 551989.],
            'PUBLIC_SURFACE_MAP_BINDING_INVALID')
    return raw, city


def load_registry(path=REGISTRY, expected=REGISTRY_SHA256):
    data=decode(read(path,maximum=100000,expected=expected))
    require(isinstance(data,dict) and data.get('schemaVersion')==1 and data.get('scope')=='PUBLIC_CURRENT_BASELINE_ONLY'
            and isinstance(data.get('models'),list) and len(data['models'])<=128,'PUBLIC_SURFACE_REGISTRY_INVALID')
    models={}
    for model in data['models']:
        require(isinstance(model,dict) and isinstance(model.get('id'),str)
                and re.fullmatch(r'[a-z0-9-]{1,80}',model['id'])
                and model['id'] not in models and model.get('classification')==CLASSIFICATION
                and isinstance(model.get('name'),str) and 0<len(model['name'])<=120
                and all(isinstance(model.get(k),str) and re.fullmatch('[a-f0-9]{64}',model[k]) for k in
                        ('inputBundleSha256','numericalPolicySha256')), 'PUBLIC_SURFACE_REGISTRY_INVALID')
        bounds=model.get('bounds')
        require(isinstance(bounds,list) and len(bounds)==4
                and all(type(v) in (int,float) and math.isfinite(v) and abs(v)<=60000 for v in bounds)
                and bounds[0]<bounds[2] and bounds[1]<bounds[3], 'PUBLIC_SURFACE_REGISTRY_INVALID')
        models[model['id']]=model
    return models


def load_bundle(model, root=ROOT/'data/public-surface'):
    directory=safe_path(root,model['inputBundleSha256'])
    manifest=decode(read(directory/'manifest.json',expected=model['inputBundleSha256']))
    files=manifest.get('files')
    require(manifest.get('schemaVersion')==1 and isinstance(files,dict) and 3<=len(files)<=10000
            and {'recipe.json','numerical-policy.json','input-evidence.json'}<=files.keys(),
            'PUBLIC_SURFACE_BUNDLE_INVALID')
    for name,expected in files.items():
        require(isinstance(expected,str) and re.fullmatch('[a-f0-9]{64}',expected),
                'PUBLIC_SURFACE_BUNDLE_INVALID')
        read(safe_path(directory,name),expected=expected)
    require(files['numerical-policy.json']==model['numericalPolicySha256'],'PUBLIC_SURFACE_POLICY_MISMATCH')
    recipe=decode(read(directory/'recipe.json'))
    evidence=decode(read(directory/'input-evidence.json'))
    required={'horizontalReference','verticalReference','terrain','network','assets','externalBoundaries',
              'dryWetInitializationComparison','longerWarmupComparison'}
    require(evidence.get('schemaVersion')==1 and evidence.get('classification')==CLASSIFICATION
            and evidence.get('modelTemplateSha256')==sha(encode(recipe['model']))
            and evidence.get('startUtc')==recipe['startUtc']
            and evidence.get('evaluationStartUtc')==recipe['evaluationStartUtc']
            and isinstance(evidence.get('references'),dict) and set(evidence['references'])==required
            and all(isinstance(name,str) and name in files for name in evidence['references'].values()),
            'PUBLIC_SURFACE_EVIDENCE_REFERENCES_REQUIRED')
    return directory,manifest,recipe


def atomic_json(path, value):
    path=Path(path)
    safe_path(path.parent,path.name)
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name('.'+path.name+'.'+uuid.uuid4().hex)
    try:
        with temporary.open('xb') as stream:
            stream.write(encode(value));stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,path)
        fd=os.open(path.parent,os.O_RDONLY)
        try:os.fsync(fd)
        finally:os.close(fd)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def locked(path, *, blocking=False):
    path=Path(path)
    safe_path(path.parent,path.name)
    path.parent.mkdir(parents=True,exist_ok=True)
    fd=os.open(path,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    acquired=False
    try:
        require(stat.S_ISREG(os.fstat(fd).st_mode),'PUBLIC_SURFACE_LOCK_INVALID')
        try:
            fcntl.flock(fd,fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
            acquired=True
        except BlockingIOError:
            pass
        yield acquired
    finally:
        if acquired:fcntl.flock(fd,fcntl.LOCK_UN)
        os.close(fd)
