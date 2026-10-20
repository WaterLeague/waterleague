"""고정 작업 해시와 원 산출물을 확인한 연결 계산 결과 읽기."""
import hashlib
import json
import math
from copy import deepcopy
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
    identity = {'network': network_result['engine'], 'surface': surface_result['engine'],
                'couplingCodeSha256': coupled_result['codeSha256'],
                'numericalConfiguration': coupled_result['networkNumericalConfiguration']}
    # 새 지표 설정을 고정하되 기존 보관 결과의 식별자는 소급 변경하지 않는다.
    if 'surfaceNumericalConfiguration' in coupled_result:
        identity['surfaceNumericalConfiguration'] = coupled_result['surfaceNumericalConfiguration']
    if 'networkRainfall' in coupled_result:
        identity['networkRainfallAdapterSha256'] = coupled_result['networkRainfall']['adapterSha256']
        identity['directRainfallAdapters'] = coupled_result['observedRainfall']['directResponse']
    if 'initialization' in coupled_result:
        identity['initializationAdapterSha256'] = coupled_result['initialization']['adapterSha256']
    if 'networkNumericalProfile' in coupled_result:
        # 시설 배치의 원 입력 해시는 엔진 식별자에 넣지 않아 동일 엔진의 전후 비교를 유지한다.
        identity['numericalProfileAdapters'] = {k: coupled_result['networkNumericalProfile'][k]
                                               for k in ('adapterSha256', 'compilerSha256')}
    if 'dryExchangeRoundoff' in coupled_result:
        identity['dryExchangePolicy'] = {k: v for k, v in coupled_result['dryExchangeRoundoff'].items()
                                       if k != 'withdrawalShortfallM3'}
    return digest(identity)


def _verify_dry_policy(model, surface, result, root):
    detail = result.get('dryExchangeRoundoff')
    if model.get('dryExchangePolicy') is None:
        require(detail is None, 'EVALUATION_DRY_POLICY_MISMATCH')
        return
    from waterleague_sim.engine.surface_exchange import (
        DRY_EXCHANGE_POLICY, DRY_TRANSFER_TOLERANCE_M3, DRY_TOTAL_TOLERANCE_M3)
    policy = {'policy': DRY_EXCHANGE_POLICY, 'maximumTransferShortfallM3': DRY_TRANSFER_TOLERANCE_M3,
              'maximumRunShortfallM3': DRY_TOTAL_TOLERANCE_M3}
    require(model['dryExchangePolicy'] == DRY_EXCHANGE_POLICY and isinstance(detail, dict)
            and all(detail.get(k) == v for k, v in policy.items())
            and detail == surface.get('exchange', {}).get('dryExchangeRoundoff')
            and type(detail.get('withdrawalShortfallM3')) in (int, float)
            and 0 <= detail['withdrawalShortfallM3'] <= DRY_TOTAL_TOLERANCE_M3
            and 'surface/dry-exchange-policy.json' in result['files']
            and _read(root/'surface/dry-exchange-policy.json') == policy,
            'EVALUATION_DRY_POLICY_MISMATCH')


def _verify_initialization(model, network, surface, result, root):
    if 'initialization' not in model:
        require('initialization' not in result, 'EVALUATION_INITIALIZATION_CONTEXT_MISMATCH')
        return model
    from waterleague_sim.engine.flood_errors import FloodModelError
    from waterleague_sim.forcing.coupled_initialization import METHOD, digest as input_digest, evaluation_ledger
    required = ('initialized-coupled-input.json', 'initialization-forcing.json',
                'evaluation-initial-state.json', 'evaluation-final-state.json')
    require(all(name in result['files'] for name in required), 'EVALUATION_INITIALIZATION_ARTIFACT_MISSING')
    prepared, forcing, origin, final = [_read(root/name) for name in required]
    summary = result.get('initialization')
    require(isinstance(model['initialization'], dict)
            and type(model['initialization'].get('days')) is int
            and model['initialization']['days'] in (7, 14, 28), 'EVALUATION_INITIALIZATION_CONTEXT_MISMATCH')
    seconds = model['initialization']['days']*86400
    require(isinstance(summary, dict) and all(summary.get(k) == v for k, v in forcing.items())
            and forcing['method'] == model['initialization'].get('method') == METHOD
            and seconds in (7*86400, 14*86400, 28*86400) and forcing['warmupSeconds'] == seconds
            and forcing['evaluationSeconds'] == model['durationSeconds']
            and forcing['requestSha256'] == input_digest(model)
            and forcing['preparedModelSha256'] == input_digest(prepared)
            and forcing['network']['originalSha256'] == hashlib.sha256(model['network']['inputText'].encode()).hexdigest()
            and forcing['network']['derivedSha256'] == hashlib.sha256(prepared['network']['inputText'].encode()).hexdigest()
            and forcing['scoreExcludesWarmup'] is True
            and forcing['statePolicy'] == 'SAME_LIVE_ENGINES_NO_STATE_TRANSPLANT',
            'EVALUATION_INITIALIZATION_CONTEXT_MISMATCH')
    expected = deepcopy(model)
    expected.pop('initialization')
    expected['network']['inputText'] = prepared['network']['inputText']
    expected['durationSeconds'] += seconds
    expected['surface'].update(startUtc=forcing['network']['startUtc'], durationSeconds=expected['durationSeconds'])
    expected['surface']['evaporation'].update(type='ARCHIVED_ANTECEDENT_AND_FAO56',
                                             antecedentReference=model['initialization']['weatherReference'])
    expected['observedRainfall'].update(startUtc=forcing['network']['startUtc'],
        evaluationStartUtc=model['observedRainfall']['startUtc'],
        initialization=model['initialization'] | {'method': 'OBSERVED_ANTECEDENT_CONTINUOUS_V1'})
    for key in ('startMilliseconds', 'endMilliseconds'):
        expected['evaluationMetrics'][key] += seconds*1000
    require(expected == prepared and final['network'] == network['final']
            and final['surface']['surface'] == surface['final']
            and final['surfaceExchange'] == surface['exchange']
            and origin['network']['totals']['timeSeconds'] == seconds
            and final['network']['totals']['timeSeconds'] == expected['durationSeconds'],
            'EVALUATION_INITIALIZATION_STATE_MISMATCH')
    try:
        ledger = evaluation_ledger(origin, final)
    except FloodModelError:
        raise EvaluationError('EVALUATION_INITIALIZATION_LEDGER_INVALID') from None
    require(summary.get('evaluationLedger') == ledger
            and (ledger['numericalStatus'] == 'PASSED' or result['numericalStatus'] == 'FAILED'),
            'EVALUATION_INITIALIZATION_LEDGER_MISMATCH')
    return prepared


def _verify_surface_policy(model, surface, result, root):
    configuration = surface.get('numericalConfiguration')
    require(configuration == result.get('surfaceNumericalConfiguration'), 'EVALUATION_CONTEXT_MISMATCH')
    if model.get('surface', {}).get('schemaVersion') != 2:
        return
    require(isinstance(configuration, dict)
            and configuration.get('policyVersion') == 'ANUGA_DE0_INSCRIBED_RADIUS_v2',
            'EVALUATION_SURFACE_POLICY_MISMATCH')
    quality = surface.get('numericalQuality')
    require(isinstance(quality, dict) and quality == result.get('surfaceNumericalQuality')
            and quality.get('policyVersion') == 'SURFACE_NATIVE_BALANCE_v1'
            and is_hash(quality.get('sourceSha256'))
            and quality['sourceSha256'] == surface['engine'].get('qualityAdapterSha256')
            and 'surface-quality.json' in surface['files']
            and _read(root / 'surface/surface-quality.json') == quality,
            'EVALUATION_SURFACE_QUALITY_MISMATCH')
    require(quality.get('status') in ('PASSED', 'FAILED')
            and (surface['numericalStatus'] != 'PASSED'
                 or quality['status'] == 'PASSED' and quality.get('failureCode') is None),
            'EVALUATION_ENGINE_STATUS_MISMATCH')
    if surface['evaluationMetrics']['complete']:
        time = quality.get('lastInternalTimeSeconds')
        require(type(time) in (int, float) and math.isfinite(time)
                and math.isclose(time, model['durationSeconds'], abs_tol=1e-8, rel_tol=0),
                'EVALUATION_SURFACE_TIME_MISMATCH')


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


def _verify_connected_facilities(model, network, result, root):
    if 'connectedFacilityDesign' not in model:
        require('connectedFacilities' not in result, 'EVALUATION_FACILITY_CONTEXT_MISMATCH')
        return
    required = ('connected-facility-design.json', 'facility-network.inp', 'connected-facility-initial.json')
    require(all(name in result['files'] for name in required), 'EVALUATION_FACILITY_ARTIFACT_MISSING')
    detail = result.get('connectedFacilities')
    design = _read(root / required[0])
    if 'connectedCisternDesign' in model:
        from ..engine.coupled_cistern import facilities
        raw, expected = facilities(model['network']['inputText'].encode(),
            model['connectedFacilityDesign'], _read(root/'connected-cistern-design.json'))
        require(design == expected and (root/'facility-network.inp').read_bytes() == raw,
                'EVALUATION_CISTERN_FACILITY_COMPOSITION_MISMATCH')
        source_design = design.get('sourceDesign', design['design'])
        source_hash = expected['originalSha256']
    else:
        source_design = design['design']
        source_hash = hashlib.sha256(model['network']['inputText'].encode()).hexdigest()
    require(isinstance(detail, dict) and detail.get('design') == design
            and source_design == model['connectedFacilityDesign']
            and design['originalSha256'] == source_hash
            and design['derivedSha256'] == result['files']['facility-network.inp']
            and network['engine'].get('facilityObserverVersion') == 1
            and detail.get('initial') == network['initial']['facilities'] == _read(root / required[2])
            and detail.get('final') == network['final']['facilities']
            and detail.get('quality') == network['facilityQuality']
            and detail.get('routingTimeSeconds') == network['final']['totals']['timeSeconds']
            and detail.get('scope') == 'SEPARATE_NATIVE_HYDROLOGY_BALANCE_NOT_EVALUATION_WINDOW_METRICS'
            and detail.get('routingSurfaceBalanceIncludesFacilityStorage') is False
            and detail.get('routingSurfaceBalanceAddsFacilityOutflows') is False,
            'EVALUATION_FACILITY_CONTEXT_MISMATCH')
    failed = [row['swmmId'] for row in detail['final'] if row['numericalStatus'] != 'PASSED']
    require(detail['quality'].get('failedFacilityIds') == failed
            and detail['quality'].get('status') == ('FAILED' if failed else 'PASSED')
            and (not failed or network['numericalStatus'] == result['numericalStatus'] == 'FAILED'),
            'EVALUATION_FACILITY_STATUS_MISMATCH')


def _verify_connected_storage(model, network, result, root, original_model=None):
    if 'connectedStorageDesign' not in model:
        require('connectedStorage' not in result, 'EVALUATION_STORAGE_CONTEXT_MISMATCH')
        require('connected-design-composition.json' not in result['files']
                and 'composed-network.inp' not in result['files'], 'EVALUATION_COMPOSITION_CONTEXT_MISMATCH')
        return model
    from waterleague_sim.engine.connected_storage import compile_storage, result_summary
    from waterleague_sim.engine.flood_errors import FloodModelError
    required = ('connected-storage-design.json', 'storage-network.inp', 'network/network.inp')
    require(all(name in result['files'] for name in required), 'EVALUATION_STORAGE_ARTIFACT_MISSING')
    metadata = _read(root/required[0])
    raw = (root/required[1]).read_bytes()
    detail = result.get('connectedStorage')
    original_model = model if original_model is None else original_model
    source_raw = original_model['network']['inputText'].encode()
    require(isinstance(detail, dict) and detail.get('design') == metadata
            and metadata['design'] == model['connectedStorageDesign']
            and metadata['sourceNetworkSha256'] == hashlib.sha256(source_raw).hexdigest()
            and metadata['derivedNetworkSha256'] == file_digest(root/required[1]),
            'EVALUATION_STORAGE_CONTEXT_MISMATCH')
    try:
        compiled, expected = compile_storage(source_raw, model['connectedStorageDesign'])
        composed = compiled
        if 'surfaceBasinDesign' in original_model:
            from waterleague_sim.engine.storage_composition import compose_storage
            require(all(name in result['files'] for name in
                ('connected-design-composition.json', 'composed-network.inp')),
                'EVALUATION_COMPOSITION_ARTIFACT_MISSING')
            composed, proof = compose_storage(original_model, model, compiled, expected)
            saved_proof = _read(root/'connected-design-composition.json')
            proof['compilerSha256'] = saved_proof['compilerSha256']
            require(proof == saved_proof and is_hash(saved_proof['compilerSha256'])
                and composed == (root/'composed-network.inp').read_bytes(),
                'EVALUATION_COMPOSITION_CONTEXT_MISMATCH')
        else:
            require('connected-design-composition.json' not in result['files']
                and 'composed-network.inp' not in result['files'], 'EVALUATION_COMPOSITION_CONTEXT_MISMATCH')
        from waterleague_sim.ingestion.published_network import records
        identifiers = {row['nodeId'].upper() for row in metadata['facilities']}
        identifiers |= {row['nodeId'].upper()+'_A' for row in metadata['facilities']}
        identifiers |= {port['linkId'].upper() for row in metadata['facilities'] for port in row['ports'].values()}
        def design_rows(data):
            return {section: [row['tokens'] for row in rows
                    if row['tokens'][0].upper() in identifiers]
                    for section, rows in records(data)[1].items()
                    if any(row['tokens'][0].upper() in identifiers for row in rows)}
        require(design_rows(compiled) == design_rows((root/required[2]).read_bytes()),
                'EVALUATION_STORAGE_NATIVE_INPUT_MISMATCH')
        # 이전 코드 해시는 원 묶음에 보존하고 입력·제원·계산 의미의 일치만 다시 확인한다.
        expected['compilerSha256'] = metadata['compilerSha256']
        origin = None
        if 'initialization' in model:
            require('evaluation-initial-state.json' in result['files'], 'EVALUATION_STORAGE_ARTIFACT_MISSING')
            origin = _read(root/'evaluation-initial-state.json')['network']
        summary = result_summary(metadata, network['initial'], network['final'], origin)
    except FloodModelError:
        raise EvaluationError('EVALUATION_STORAGE_INPUT_INVALID') from None
    require(compiled == raw and expected == metadata and is_hash(metadata['compilerSha256'])
            and detail == summary, 'EVALUATION_STORAGE_CONTEXT_MISMATCH')
    require(summary['numericalStatus'] == 'PASSED' or result['numericalStatus'] == 'FAILED',
            'EVALUATION_STORAGE_STATUS_MISMATCH')
    return model | {'network': model['network'] | {'inputText': composed.decode()}}


def _verify_surface_basins(model, surface, result, root):
    if 'surfaceBasinDesign' not in model:
        require('surfaceBasins' not in result, 'EVALUATION_BASIN_CONTEXT_MISMATCH')
        return model
    from waterleague_sim.engine.surface_basin import compile_basin, result_summary
    from waterleague_sim.engine.flood_errors import FloodModelError
    required = ('surface-basin-design.json', 'basin-coupled-input.json')
    require(all(name in result['files'] for name in required), 'EVALUATION_BASIN_ARTIFACT_MISSING')
    metadata, prepared = [_read(root/name) for name in required]
    try:
        expected_model, expected = compile_basin(model)
        expected['compilerSha256'] = metadata['compilerSha256']
        if expected['schemaVersion'] == 2:
            require(len(expected['facilities']) == len(metadata['facilities']), 'EVALUATION_BASIN_CONTEXT_MISMATCH')
            for current, stored in zip(expected['facilities'], metadata['facilities']):
                code_hash = stored.get('terrainStageStorage', {}).get('implementationSha256')
                require(is_hash(code_hash), 'EVALUATION_BASIN_CONTEXT_MISMATCH')
                current['terrainStageStorage']['implementationSha256'] = code_hash
        origin = _read(root/'evaluation-initial-state.json')['surface']['surface'] if 'initialization' in model else None
        summary = result_summary(metadata, surface, origin)
    except FloodModelError:
        raise EvaluationError('EVALUATION_BASIN_INPUT_INVALID') from None
    require(prepared == expected_model and expected == metadata and is_hash(metadata['compilerSha256'])
        and result.get('surfaceBasins') == summary, 'EVALUATION_BASIN_CONTEXT_MISMATCH')
    # 실행 지형·재료·면적 소유권을 원 요청의 설계 파생과 직접 대조한다.
    actual = _read(root/'surface/surface-input.json')
    for key in ('verticesM', 'triangles', 'elevationM', 'manningN', 'rainfallOwner', 'initialDepthM',
                'infiltration', 'boundaryEdges', 'boundaryConditions', 'designTerrainProvenance'):
        require(actual[key] == prepared['surface'][key], 'EVALUATION_BASIN_NATIVE_SURFACE_MISMATCH')
    from waterleague_sim.ingestion.published_network import records
    names = {row['portId'].upper()+suffix for row in metadata['facilities'] for suffix in ('_D', '_O')}
    def rows(text):
        return {name: [r['tokens'] for r in values if r['tokens'][0].upper() in names]
                for name, values in records(text.encode())[1].items()
                if any(r['tokens'][0].upper() in names for r in values)}
    require(rows(prepared['network']['inputText']) == rows((root/'network/network.inp').read_text()),
            'EVALUATION_BASIN_NATIVE_NETWORK_MISMATCH')
    return prepared


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
        original_model = model
        from .rainfall_coverage import verify as verify_coverage
        verify_coverage(model, surface, result, root, _read, file_digest)
        model = _verify_surface_basins(model, surface, result, root)
        model = _verify_connected_storage(model, network, result, root, original_model)
        from .pumps import verify_connected_pumps
        model = verify_connected_pumps(original_model, model, network, result, root, _read)
        from .coupled_numerics import verify_numerical_profile
        model = verify_numerical_profile(model, network, result, root, _read)
        model = _verify_initialization(model, network, surface, result, root)
        _verify_dry_policy(model, surface, result, root)
        _verify_surface_policy(model, surface, result, root)
        from .live_rainfall import verify as verify_live_rainfall
        model = verify_live_rainfall(model, network, result, root, _read)
        from .cistern import verify as verify_cistern
        model = verify_cistern(original_model, model, network, result, root, _read)
        _verify_connected_facilities(model, network, result, root)
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
