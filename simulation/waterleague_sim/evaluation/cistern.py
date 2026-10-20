"""결합 이용조의 원 요청·실행 입력·평가 시각 원장 대조."""
from .exception import require
from ..engine.coupled_cistern import compile, facilities
from ..engine.connected_storage import result_summary, storage_ledger


def verify(original, model, network, result, root, read):
    names = ('connected-cistern-design.json', 'cistern-network.inp',
             'cistern-evaluation-initial.json', 'cistern-evaluation-final.json')
    if 'connectedCisternDesign' not in original:
        require('connectedCistern' not in result and not any(n in result['files'] for n in names),
                'EVALUATION_CISTERN_CONTEXT_MISMATCH')
        return model
    require(all(n in result['files'] for n in names), 'EVALUATION_CISTERN_ARTIFACT_MISSING')
    raw, metadata = compile(original, model['network'])
    saved = read(root/names[0])
    require(metadata == saved and (root/names[1]).read_bytes() == raw,
            'EVALUATION_CISTERN_COMPOSITION_MISMATCH')
    physical = raw
    if 'connectedFacilityDesign' in model:
        physical, _ = facilities(raw, model['connectedFacilityDesign'], metadata)
    actual = 'network/network-original.inp' if network.get('stageBoundaries') else 'network/network.inp'
    require((root/actual).read_bytes() == physical, 'EVALUATION_CISTERN_NATIVE_INPUT_MISMATCH')
    origin, final = [read(root/n) for n in names[2:]]
    spec = model['evaluationMetrics']
    require(origin['totals']['timeSeconds'] * 1000 == spec['startMilliseconds']
            and final['totals']['timeSeconds'] * 1000 == spec['endMilliseconds'],
            'EVALUATION_CISTERN_CLOCK_MISMATCH')
    if spec['startMilliseconds'] == 0:
        require(origin == network['initial'], 'EVALUATION_CISTERN_INITIAL_STATE_MISMATCH')
    if 'initialization' in original:
        require(origin == read(root/'evaluation-initial-state.json')['network']
                and final == read(root/'evaluation-final-state.json')['network'],
                'EVALUATION_CISTERN_INITIALIZATION_STATE_MISMATCH')
    if spec['endMilliseconds'] == model['durationSeconds']*1000:
        require(final == network['final'], 'EVALUATION_CISTERN_FINAL_STATE_MISMATCH')
    expected = result_summary(metadata, network['initial'], network['final'])
    expected['evaluationLedger'] = storage_ledger(metadata, origin, final)
    if expected['evaluationLedger']['numericalStatus'] != 'PASSED':
        expected['numericalStatus'] = 'FAILED'
    require(result.get('connectedCistern') == expected,
            'EVALUATION_CISTERN_LEDGER_MISMATCH')
    require(expected['numericalStatus'] == 'PASSED' or result['numericalStatus'] == 'FAILED',
            'EVALUATION_CISTERN_STATUS_MISMATCH')
    return model | {'network': model['network'] | {'inputText': raw.decode()}}
