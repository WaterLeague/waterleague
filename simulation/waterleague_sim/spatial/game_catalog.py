"""원형 공간과 독립된 보관 관측 창의 현재 게임 결속 조회."""
from functools import lru_cache
import copy
import hashlib
import json
import re
import os
import stat

from ..engine.swmm import ROOT
from .play_catalog import NativeCatalogError

DIRECTORY = ROOT / 'backend/src/main/resources/native-game/v2'
SHA256 = 'f08b92fa00db08126e86b379583299a831764b958a4f131de4647ebde95e6fdb'


def _read(name, maximum=512 * 1024):
    path = DIRECTORY / name
    try:
        if any(part.is_symlink() for part in (path, *path.parents)):
            raise NativeCatalogError('NATIVE_GAME_SOURCE_INVALID')
        with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), 'rb') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or not 1 <= info.st_size <= maximum:
                raise NativeCatalogError('NATIVE_GAME_SOURCE_INVALID')
            raw = stream.read(maximum + 1)
        if len(raw) > maximum:
            raise NativeCatalogError('NATIVE_GAME_SOURCE_INVALID')
        return raw
    except OSError:
        raise NativeCatalogError('NATIVE_GAME_SOURCE_INVALID') from None


@lru_cache(maxsize=1)
def _catalog():
    raw = _read('catalog.json')
    if hashlib.sha256(raw).hexdigest() != SHA256:
        raise NativeCatalogError('NATIVE_GAME_CATALOG_INVALID')
    value = json.loads(raw)
    if value['id'] != 'SEOUL_NGII_GAME_V2' or len(value['regions']) != 25 or len(value['models']) != 100:
        raise NativeCatalogError('NATIVE_GAME_CATALOG_INVALID')
    return value


def catalog():
    return copy.deepcopy(_catalog())


def regions():
    return {row['districtId']: row for row in catalog()['regions']}


@lru_cache(maxsize=100)
def forcing(model_hash):
    entry = next((row for row in _catalog()['models'] if row['sha256'] == model_hash), None)
    if entry is None or entry['file'] != 'models/' + entry['id'] + '.json' or not re.fullmatch(
            r'ngii-11\d{3}-(default|seoul-\d{8})-\d{1,5}', entry['id']):
        raise NativeCatalogError('NATIVE_FORCING_NOT_FOUND')
    raw = _read(entry['file'], 256 * 1024)
    if len(raw) != entry['bytes'] or hashlib.sha256(raw).hexdigest() != model_hash:
        raise NativeCatalogError('NATIVE_FORCING_INVALID')
    value = json.loads(raw)
    if (value['kind'] != 'OBSERVED_FORCING_BINDING' or value['districtId'] != entry['districtId']
            or value['id'] != entry['id'] or value['mapId'] != 'seoul-ngii-v1-' + entry['districtId']
            or value['siteCatalogSha256'] != _catalog()['siteCatalogSha256']):
        raise NativeCatalogError('NATIVE_FORCING_INVALID')
    return raw


def climate_binding(name, model_hash):
    if name not in ('evaporation', 'antecedent'):
        raise NativeCatalogError('NATIVE_CLIMATE_BINDING_INVALID')
    reference = catalog()['climateBindings'][name]
    raw = _read(name + '.json')
    if reference['file'] != name + '.json' or hashlib.sha256(raw).hexdigest() != reference['sha256']:
        raise NativeCatalogError('NATIVE_CLIMATE_BINDING_INVALID')
    value = json.loads(raw)
    entries = [row for row in value['entries'] if model_hash in row['modelHashes']]
    if len(entries) != 1:
        raise NativeCatalogError('NATIVE_CLIMATE_BINDING_INVALID')
    return value, entries[0]
