"""원 집수 경계·관측 강우를 보존한 수리 이용조와 지표 결합."""
from copy import deepcopy

from .cistern_network import compile_cistern
from .connected_facilities import compile_design
from .flood_errors import require
from ..ingestion.published_network import digest
from ..watershed_cistern import prepare_lids


def facilities(raw, design, metadata=None):
    if metadata is None:
        return compile_design(raw, design)
    host = metadata['catchmentPartition']['hostId']
    shared = [p for p in design['placements'] if p['subcatchmentId'].upper() == host.upper()]
    require(not shared or metadata['schemaVersion'] == 3,
            'COUPLED_CISTERN_SHARED_PARTITION_REQUIRED')
    prepared, execution, assignments, width = prepare_lids(raw, design, metadata)
    result, detail = compile_design(prepared, execution)
    if assignments:
        detail.update(sourceDesign=deepcopy(design), sourceCatchmentAssignments=assignments,
                      sharedCatchmentWidth=width)
    return result, detail


def validate(model):
    require(model.get('evaluationMetrics') is not None, 'COUPLED_CISTERN_METRICS_REQUIRED')
    require(not any(k in model for k in ('connectedStorageDesign',
        'connectedPumpDesign', 'surfaceBasinDesign', 'networkNumericalProfile')),
        'COUPLED_CISTERN_COMPOSITION_UNSUPPORTED')
    raw, metadata = compile_cistern(model['network']['inputText'].encode(), model['connectedCisternDesign'])
    if 'connectedFacilityDesign' in model:
        facilities(raw, model['connectedFacilityDesign'], metadata)
    return raw, metadata


def compile(model, network):
    raw, metadata = validate(model)
    original = model['network']['inputText'].encode()
    prepared = network['inputText'].encode()
    initialization = None
    if 'initialization' in model:
        from ..forcing.network_initialization import prepare_initialized_network, METHOD
        initialized = prepare_initialized_network(model['network'], model['observedRainfall'],
            model['initialization'] | {'method': METHOD})
        require(network == initialized.model, 'COUPLED_CISTERN_INITIALIZATION_BINDING_MISMATCH')
        initialization = {
            'method': 'CONTINUOUS_CISTERN_STATE_FROM_OBSERVED_ANTECEDENT_V1',
            'forcingSha256': initialized.summary['derivedSha256'],
            'warmupSeconds': initialized.summary['warmupSeconds'],
            'evaluationSeconds': initialized.summary['evaluationSeconds'],
            'initialDepthAppliesAt': initialized.summary['startUtc'],
            'evaluationStatePolicy': 'SAME_LIVE_ENGINE_NO_STORAGE_RESET',
        }
    elif prepared != original:
        from ..forcing.live_network_rainfall import compile_network
        expected, _ = compile_network(model['network'], model['observedRainfall'])
        require(network == expected, 'COUPLED_CISTERN_RAIN_BINDING_MISMATCH')
    if prepared != original:
        # 검증한 관측 파생본만 재결속하며 선행 계산과 사건 사이에 저류를 초기화하지 않는다.
        raw, metadata = compile_cistern(prepared,
            model['connectedCisternDesign'] | {'sourceNetworkSha256': digest(prepared)})
    metadata['coupledBinding'] = {
        'method': 'SOURCE_BOUND_CISTERN_RAINFALL_COMPOSITION_V1',
        'originalNetworkSha256': digest(original),
        'preparedNetworkSha256': digest(prepared),
        'sourceDesign': deepcopy(model['connectedCisternDesign']),
        **({'sourceRainfallCoverage': deepcopy(model['networkRainfallCoverage'])}
           if 'networkRainfallCoverage' in model else
           {'sourceRainfallTriangles': deepcopy(model['networkRainfallTriangles'])}),
        'partitionGeometry': 'UNIFORM_DESIGN_WITHIN_ORIGINAL_CATCHMENT_NOT_SURVEYED_ROOF',
        'surfaceRainfallOwnershipUnchanged': True,
    }
    if initialization is not None:
        metadata['coupledBinding']['initialization'] = initialization
    return raw, metadata
