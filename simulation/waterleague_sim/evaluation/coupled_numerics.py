"""원 모형과 명시적 수치 파생 및 실제 실행 설정 대조."""
from .exception import EvaluationError, require
from .values import is_hash


def verify_numerical_profile(model, network, result, root, read):
    if 'networkNumericalProfile' not in model:
        require('networkNumericalProfile' not in result, 'EVALUATION_NUMERICAL_PROFILE_CONTEXT_MISMATCH')
        return model
    from ..engine.coupled_numerics import compile
    from ..engine.flood_errors import FloodModelError
    from ..ingestion.published_network import records
    names = ('network-numerical-profile.json', 'numerical-coupled-input.json', 'numerical-network.inp')
    require(all(name in result['files'] for name in names), 'EVALUATION_NUMERICAL_PROFILE_ARTIFACT_MISSING')
    metadata, prepared = [read(root/name) for name in names[:2]]
    try:
        expected, detail = compile(model)
    except FloodModelError:
        raise EvaluationError('EVALUATION_NUMERICAL_PROFILE_INPUT_INVALID') from None
    detail['adapterSha256'] = metadata['adapterSha256']
    detail['compilerSha256'] = metadata['compilerSha256']
    require(is_hash(metadata['adapterSha256']) and is_hash(metadata['compilerSha256'])
        and expected == prepared and detail == metadata
        and metadata == result.get('networkNumericalProfile')
        and (root/names[2]).read_bytes() == prepared['network']['inputText'].encode(),
        'EVALUATION_NUMERICAL_PROFILE_CONTEXT_MISMATCH')
    options = model['networkNumericalProfile']['options']
    actual = {row['tokens'][0].upper(): row['tokens'][1] for row in
              records((root/'network/network.inp').read_bytes())[1]['OPTIONS']}
    declared = network['numericalConfiguration']['declaredInputOptions']
    require(all(actual.get(k) == declared.get(k) == str(v) for k, v in options.items()),
            'EVALUATION_NUMERICAL_PROFILE_NATIVE_MISMATCH')
    fields = {'SURCHARGE_METHOD': 'surchargeMethod', 'ROUTING_STEP': 'maximumRoutingStepSeconds',
        'MINIMUM_STEP': 'minimumRoutingStepSeconds', 'MAX_TRIALS': 'maximumTrials'}
    require(all(network['numericalConfiguration'].get(fields[k]) == v for k, v in options.items()),
            'EVALUATION_NUMERICAL_PROFILE_EFFECTIVE_MISMATCH')
    return prepared
