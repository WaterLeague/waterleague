"""펌프 합성 입력과 선행·평가 운전 기록의 재현 결속 검사."""
import math

from .exception import EvaluationError, require
from .values import is_hash


def _operation(operation, identifiers, duration):
    from waterleague_sim.engine.pump_network import FIELDS
    require(isinstance(operation, dict)
        and operation.get('method') == 'NATIVE_ROUTING_STEP_PUMP_OBSERVER_V1'
        and operation.get('volumeIntegration') == 'TRAPEZOIDAL_INTERNAL_TRANSFER_NOT_EXTERNAL_OUTFLOW'
        and operation.get('shaftPowerIntegration') == 'END_OF_NATIVE_STEP_RECTANGLE_MANUFACTURER_P_Q_CURVE'
        and operation.get('rankingEligible') is False
        and isinstance(operation.get('pumps'), list), 'EVALUATION_PUMP_OPERATION_INVALID')
    rows = operation['pumps']
    require(len(rows) == len(identifiers) and {r['linkId'] for r in rows} == identifiers,
            'EVALUATION_PUMP_OPERATION_INVALID')
    for row in rows:
        require(all(type(row.get(k)) in (int, float) and math.isfinite(row[k])
                    and (row[k] >= 0 or k in ('minimumOperatingHeadM', 'maximumOperatingHeadM'))
                    for k in FIELDS)
            and all(row[k] == int(row[k]) for k in ('routingSteps', 'startCount'))
            and math.isclose(row['observedSeconds'], duration, abs_tol=1e-7, rel_tol=0)
            and all(row[k] <= duration+1e-7 for k in ('runningSeconds', 'flowingSeconds',
                'outsideHeadCurveSeconds', 'outsideFlowCurveSeconds'))
            and row['minimumOperatingHeadM'] <= row['maximumOperatingHeadM']
            and row.get('electricEnergyKwh') is None and row.get('cavitationStatus') == 'NOT_EVALUATED',
            'EVALUATION_PUMP_OPERATION_INVALID')
        valid = row['outsideHeadCurveSeconds'] == row['outsideFlowCurveSeconds'] == 0
        require(row.get('curveStatus') == ('PASSED' if valid else 'FAILED')
            and row.get('shaftEnergyKwh') == (row['inRangeShaftEnergyKwh'] if valid else None),
            'EVALUATION_PUMP_STATUS_MISMATCH')
    require(operation.get('curveStatus') == ('PASSED' if all(r['curveStatus'] == 'PASSED' for r in rows)
                                           else 'FAILED'), 'EVALUATION_PUMP_STATUS_MISMATCH')
    return {r['linkId']: r for r in rows}


def verify_connected_pumps(original, model, network, result, root, read):
    if 'connectedPumpDesign' not in original:
        require('connectedPumps' not in result and 'pumpOperation' not in network,
                'EVALUATION_PUMP_CONTEXT_MISMATCH')
        return model
    from waterleague_sim.engine.coupled_pumps import compile, summary
    from waterleague_sim.engine.connected_pumps import CATALOG_HASH
    from waterleague_sim.engine.flood_errors import FloodModelError
    from waterleague_sim.ingestion.published_network import records
    required = ('connected-pump-design.json', 'pump-coupled-input.json', 'pump-curve.json')
    require(all(name in result['files'] for name in required), 'EVALUATION_PUMP_ARTIFACT_MISSING')
    metadata, prepared = [read(root/name) for name in required[:2]]
    require(result['files']['pump-curve.json'] == CATALOG_HASH, 'EVALUATION_PUMP_CURVE_MISMATCH')
    try:
        expected_model, expected = compile(original, model)
    except FloodModelError:
        raise EvaluationError('EVALUATION_PUMP_INPUT_INVALID') from None
    # 이전 실행의 소스 해시는 보존하며 설계와 파생 입력의 의미를 재검사한다.
    for target, source, key in ((expected, metadata, 'adapterSha256'),
                               (expected['compiled'], metadata['compiled'], 'compilerSha256')):
        require(is_hash(source.get(key)), 'EVALUATION_PUMP_CONTEXT_MISMATCH')
        target[key] = source[key]
    require(expected_model == prepared and expected == metadata
        and all(network['engine'].get(k) == 1 for k in ('pumpObserverVersion', 'pumpEvaluationVersion')),
        'EVALUATION_PUMP_CONTEXT_MISMATCH')
    identifiers = {row['linkId'] for row in metadata['compiled']['facilities']}
    owned = {name.upper()+suffix for name in identifiers for suffix in ('', '_D', '_F', '_H', '_P', '_N')}
    def native_rows(raw):
        sections = records(raw)[1]
        rows = {s: [r['tokens'] for r in values if r['tokens'][0].upper() in owned]
                for s, values in sections.items()
                if any(r['tokens'][0].upper() in owned for r in values)}
        rows['FORCE_MAIN_EQUATION'] = [r['tokens'] for r in sections['OPTIONS']
                                      if r['tokens'][0].upper() == 'FORCE_MAIN_EQUATION']
        return rows
    require(native_rows(prepared['network']['inputText'].encode())
            == native_rows((root/'network/network.inp').read_bytes()),
            'EVALUATION_PUMP_NATIVE_INPUT_MISMATCH')
    operation = network.get('pumpOperation')
    require(result.get('connectedPumps') == summary(metadata, operation), 'EVALUATION_PUMP_CONTEXT_MISMATCH')
    duration = network['final']['totals']['timeSeconds']
    whole = _operation(operation, identifiers, duration)
    window = operation.get('evaluation')
    spec = network['evaluationMetrics']['specificationSha256']
    require(spec == result['evaluationMetrics']['specificationSha256'] and isinstance(window, dict),
            'EVALUATION_PUMP_WINDOW_MISMATCH')
    metrics = result['evaluationMetrics']['specification']
    start, end = (metrics[k]/1000 for k in ('startMilliseconds', 'endMilliseconds'))
    require(0 <= start < end <= duration and window.get('startSeconds') == start
        and window.get('endSeconds') == end and window.get('complete') is True
        and window.get('statePolicy') == 'CONTINUOUS_STATE_WARMUP_EXCLUDED_NO_FALSE_START',
        'EVALUATION_PUMP_WINDOW_MISMATCH')
    evaluated = _operation(window, identifiers, end-start)
    for name, row in whole.items():
        require(all(evaluated[name][k] <= row[k]+1e-7 for k in ('transferredM3', 'runningSeconds',
            'flowingSeconds', 'startCount', 'peakFlowM3s', 'outsideHeadCurveSeconds',
            'outsideFlowCurveSeconds', 'inRangeShaftEnergyKwh', 'routingSteps')),
            'EVALUATION_PUMP_WINDOW_MISMATCH')
        node = network['final']['nodes'][name+'_D']
        require(row.get('deliveryNodeId') == name+'_D' and row.get('deliveryFloodingM3') == node['floodingM3']
            and row.get('deliveryStatus') == ('PASSED' if node['floodingM3'] <= 1e-9 else 'FAILED'),
            'EVALUATION_PUMP_STATUS_MISMATCH')
    require(operation.get('deliveryStatus') == ('PASSED' if all(r['deliveryStatus'] == 'PASSED'
        for r in whole.values()) else 'FAILED'), 'EVALUATION_PUMP_STATUS_MISMATCH')
    passed = operation['curveStatus'] == operation['deliveryStatus'] == window['curveStatus'] == 'PASSED'
    require(passed or network['numericalStatus'] == result['numericalStatus'] == 'FAILED',
            'EVALUATION_PUMP_STATUS_MISMATCH')
    return prepared
