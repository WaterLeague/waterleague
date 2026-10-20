"""공개 관망의 검증된 원 계산 파일만 재사용하는 제한 캐시."""
import os
from pathlib import Path
import platform
import sys

from . import result_cache as cache
from .engine.flood_errors import require
from .engine.flood_process import EngineProcess
from .engine.swmm import ROOT

FILES = frozenset(('network.inp', 'network.rpt', 'network.out',
                   'network-frames.jsonl', 'network-result.json'))
RESULT_FIELDS = frozenset((
    'schemaVersion', 'engine', 'inputUnits', 'internalVolumeConversionM3PerFt3',
    'durationSeconds', 'evaluationSeconds', 'calendarDurationSeconds', 'complete',
    'timeWindowPolicy', 'calendarShortfallSeconds', 'initial', 'final', 'forcing',
    'runoffContinuityPercent', 'routingContinuityPercent', 'warningCount',
    'convergence', 'numericalQuality', 'numericalConfiguration', 'numericalStatus',
    'files', 'facilityQuality', 'evaluationMetrics'))


def configured_root():
    if os.environ.get('SIMULATION_CACHE_ENABLED', 'true').lower() == 'false':
        return None
    return Path(os.environ.get('WATERSHED_CACHE_PATH', ROOT/'data/private/watershed-cache'))


def implementation_hash():
    paths = sorted((ROOT/'simulation/waterleague_sim').rglob('*.py'))
    paths += [ROOT/'simulation/pyproject.toml', ROOT/'simulation/uv.lock']
    return cache.digest(cache.encoded({
        str(path.relative_to(ROOT)): cache.digest(path.read_bytes()) for path in paths}))


def identity(request, raw, engine_kind, engine):
    require(set(request) == {'modelHash', 'inputHash', 'placements'},
            'WATERSHED_CACHE_REQUEST_INVALID')
    require(cache.digest((request['modelHash']+'\n'+request['placements']).encode()) == request['inputHash'],
            'WATERSHED_INPUT_HASH_MISMATCH')
    require(engine_kind in ('facility_metrics', 'pump_network'), 'WATERSHED_CACHE_ENGINE_INVALID')
    value = {
        'schema': 1, 'scope': 'PUBLIC_NETWORK_CASE_V1',
        'modelHash': request['modelHash'], 'requestInputHash': request['inputHash'],
        'inputSha256': cache.digest(raw), 'engineKind': engine_kind, 'engine': engine,
        'implementationSha256': implementation_hash(),
        'platform': platform.platform(), 'machine': platform.machine(), 'python': sys.version,
        'frameIntervalSeconds': 300, 'nativeDuration': True,
    }
    return cache.digest(cache.encoded(value)), value


def validate(files, source):
    require(set(files) == FILES and sum(map(len, files.values())) <= cache.MAX_ENTRY_BYTES,
            'WATERSHED_CACHE_FILES_INVALID')
    result = cache.decoded(files['network-result.json'])
    fields = RESULT_FIELDS | ({'pumpOperation'} if source['engineKind'] == 'pump_network' else set())
    require(set(result) == fields and result['schemaVersion'] == 1
            and result['engine'] == source['engine']
            and result['numericalStatus'] == 'PASSED' and result['complete'] is True
            and result['timeWindowPolicy'] == 'NATIVE_DURATION_DIAGNOSTIC'
            and result['forcing'] == [] and result['evaluationMetrics']['complete'] is True,
            'WATERSHED_CACHE_RESULT_INVALID')
    require(cache.digest(files['network.inp']) == source['inputSha256']
            and result['files'] == {name: cache.digest(files[name]) for name in FILES-{'network-result.json'}},
            'WATERSHED_CACHE_BINDING_INVALID')
    return result


class NetworkCaseCache(cache.ResultCache):
    files = FILES
    marker = b'waterleague-network-case-cache-v1\n'
    validate = staticmethod(validate)


def run(request, raw, engine_kind, engine, directory, root=None):
    key, source = identity(request, raw, engine_kind, engine)
    directory = Path(directory)
    require(not directory.exists(), 'WATERSHED_CASE_DIRECTORY_EXISTS')
    store = NetworkCaseCache(root) if root is not None else None
    files = store.load(key, source) if store else None
    if files is not None:
        require(implementation_hash() == source['implementationSha256'], 'WATERSHED_CACHE_CODE_CHANGED')
        directory.mkdir(mode=0o700)
        for name, value in files.items():
            cache._write(directory/name, value)
        result = cache.decoded(files['network-result.json'])
        mode = 'REUSED'
    else:
        with EngineProcess(engine_kind, raw.decode(), directory, native_duration=True) as process:
            result = process.call('run', 300)['result']
        require(result['engine'] == engine, 'WATERSHED_CACHE_ENGINE_CHANGED')
        require(implementation_hash() == source['implementationSha256'], 'WATERSHED_CACHE_CODE_CHANGED')
        mode = 'COMPUTED'
        if store and result['numericalStatus'] == 'PASSED' and result['complete']:
            try:
                files, total = {}, 0
                for name in sorted(FILES):
                    value = cache._read(directory/name, cache.MAX_ENTRY_BYTES-total)
                    total += len(value)
                    files[name] = value
                store.store(key, source, files)
            except (OSError, ValueError):
                # 보조 캐시 실패는 완료한 계산 결과를 폐기하는 사유가 아니다.
                pass
    return result, {'schema': 1, 'scope': 'PUBLIC_NETWORK_CASE_V1',
                    'mode': mode, 'computationKey': key}
