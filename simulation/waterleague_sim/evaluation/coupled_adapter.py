"""고정 작업 해시와 원 산출물을 확인한 연결 계산 결과 읽기."""
import hashlib
import json
from pathlib import Path, PurePosixPath

from .exception import EvaluationError, require
from .service import validate_record
from .values import digest, is_hash


def file_digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def _read(path):
    require(path.stat().st_size <= 64 * 1024 * 1024, 'EVALUATION_ARTIFACT_TOO_LARGE')
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'EVALUATION_ARTIFACT_DUPLICATE_KEY')
            result[key] = value
        return result
    def reject(_):
        raise EvaluationError('EVALUATION_NUMBER_INVALID')
    return json.loads(path.read_bytes(), object_pairs_hook=pairs, parse_constant=reject)


def engine_signature(network_result, surface_result, coupled_result):
    return digest({'network': network_result['engine'], 'surface': surface_result['engine'],
                   'couplingCodeSha256': coupled_result['codeSha256'],
                   'numericalConfiguration': coupled_result['networkNumericalConfiguration']})


def _verify_files(root, files):
    require(isinstance(files, dict) and len(files) <= 100_000, 'EVALUATION_MANIFEST_INVALID')
    for name, expected in files.items():
        relative = PurePosixPath(name)
        require(not relative.is_absolute() and '..' not in relative.parts and is_hash(expected),
                'EVALUATION_ARTIFACT_PATH_INVALID')
        path = root / relative
        require(path.resolve().is_relative_to(root)
                and not any((root / Path(*relative.parts[:i])).is_symlink()
                            for i in range(1, len(relative.parts) + 1)),
                'EVALUATION_ARTIFACT_PATH_INVALID')
        require(file_digest(path) == expected, 'EVALUATION_ARTIFACT_HASH_MISMATCH')


def read_coupled_record(directory, expected_result_sha256, context):
    """context는 서버가 고정한 시나리오·관측·설계 변경 계약이며 사용자 입력이 아니다."""
    root = Path(directory).resolve()
    try:
        result_path = root / 'coupled-result.json'
        require(is_hash(expected_result_sha256) and not result_path.is_symlink()
                and file_digest(result_path) == expected_result_sha256, 'EVALUATION_RESULT_HASH_MISMATCH')
        result = _read(result_path)
        files = result['files']
        _verify_files(root, files)
        required = ('coupled-input.json', 'network/network-result.json', 'surface/surface-result.json')
        require(all(name in files for name in required), 'EVALUATION_ARTIFACT_MISSING')
        model, network, surface = [_read(root / name) for name in required]
        _verify_files(root / 'network', network['files'])
        _verify_files(root / 'surface', surface['files'])
        metrics = result['evaluationMetrics']
        require(metrics['specificationSha256'] == context['metricSpecificationSha256']
                and digest(model['evaluationMetrics']) == context['metricSpecificationSha256']
                and digest(metrics['specification']) == network['evaluationMetrics']['specificationSha256']
                    == surface['evaluationMetrics']['specificationSha256'] == context['metricSpecificationSha256']
                and result['networkNumericalConfiguration'] == network['numericalConfiguration']
                and engine_signature(network, surface, result) == context['engineSha256'],
                'EVALUATION_CONTEXT_MISMATCH')
        require(not str(model['evidence']).startswith('NUMERICAL')
                or context['evidenceClass'] == 'NUMERICAL_TEST_ONLY', 'EVALUATION_EVIDENCE_MISMATCH')
        raw = {'outwardVolumeM3': network['evaluationMetrics']['combined']['outwardVolumeM3'],
               'peakOutwardM3s': network['evaluationMetrics']['combined']['peakOutwardM3s'],
               'depthAreaTimeM3Hours': surface['evaluationMetrics']['depthAreaTimeM3Hours']}
        require(metrics['raw'] == raw, 'EVALUATION_RAW_METRICS_MISMATCH')
        require(result['numericalStatus'] != 'PASSED'
                or network['numericalStatus'] == surface['numericalStatus'] == 'PASSED',
                'EVALUATION_ENGINE_STATUS_MISMATCH')
        record = {'schemaVersion': 1, 'context': context,
                  'inputSha256': files['coupled-input.json'], 'resultSha256': expected_result_sha256,
                  'numericalStatus': result['numericalStatus'],
                  'complete': metrics['complete'] and network['complete']
                      and network['evaluationMetrics']['complete'] and surface['evaluationMetrics']['complete'],
                  'raw': raw}
        validate_record(record, context)
        return record
    except EvaluationError:
        raise
    except (OSError, ValueError, KeyError, TypeError):
        raise EvaluationError('EVALUATION_ARTIFACT_INVALID') from None
