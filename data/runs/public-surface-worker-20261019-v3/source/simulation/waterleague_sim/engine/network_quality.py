"""고정 EPA 빌드의 수렴 횟수와 수지 기준을 분리한 수치 판정."""
import ctypes as C
import math

from waterleague_sim.engine.flood_errors import require

POLICY = 'network-continuity-convergence-v2'


def configuration_state(library, declared_options):
    """기본값 적용·단위 변환 후의 엔진 설정. 실제 시설 제원과 별도 보존."""
    doubles = ('RouteStep', 'MinRouteStep', 'CourantFactor', 'MinSurfArea', 'HeadTol')
    try:
        values = {name: C.c_double.in_dll(library, name).value for name in doubles}
        method = C.c_int.in_dll(library, 'SurchargeMethod').value
        trials = C.c_int.in_dll(library, 'MaxTrials').value
    except ValueError:
        require(False, 'NETWORK_CONFIGURATION_UNAVAILABLE')
    require(all(math.isfinite(v) and v >= 0 for v in values.values())
            and values['RouteStep'] > 0 and values['MinRouteStep'] > 0
            and method in (0, 1) and trials > 0, 'NETWORK_CONFIGURATION_INVALID')
    names = ('SURCHARGE_METHOD', 'ROUTING_STEP', 'MINIMUM_STEP', 'VARIABLE_STEP',
             'MIN_SURFAREA', 'HEAD_TOLERANCE', 'MAX_TRIALS')
    return {'method': 'EPA_5_2_4_NATIVE_SETTINGS_READ_ONLY',
            'surchargeMethod': ('EXTRAN', 'SLOT')[method],
            'maximumRoutingStepSeconds': values['RouteStep'],
            'minimumRoutingStepSeconds': values['MinRouteStep'],
            'courantFactor': values['CourantFactor'],
            'minimumNumericalNodeAreaM2': values['MinSurfArea'] * .3048 ** 2,
            'headConvergenceToleranceM': values['HeadTol'] * .3048,
            'maximumTrials': trials,
            'declaredInputOptions': {key: declared_options[key] for key in names if key in declared_options},
            'defaultedInputOptions': [key for key in names if key not in declared_options]}


def convergence_state(library):
    # 해시로 고정된 5.2.4의 정수 카운터만 읽으며 엔진 메모리에 쓰지 않는다.
    try:
        steps = C.c_int.in_dll(library, 'TotalStepCount').value
        failed = C.c_int.in_dll(library, 'NonConvergeCount').value
    except ValueError:
        require(False, 'NETWORK_CONVERGENCE_COUNTER_UNAVAILABLE')
    require(0 <= failed <= steps, 'NETWORK_CONVERGENCE_COUNTER_INVALID')
    return {'method': 'EPA_5_2_4_NATIVE_COUNTERS_READ_ONLY',
            'routingSteps': steps, 'nonConvergedSteps': failed,
            'nonConvergedPercent': 100 * failed / steps if steps else None}


def routing_balance(totals):
    incoming = [totals['initialStorageM3'], totals['runoffInflowM3'], totals['rdiiInflowM3']]
    outgoing = [totals[k] for k in ('storageM3', 'floodingM3', 'evaporationM3',
                                    'seepageM3', 'reactionLossM3')]
    for key in ('dryWeatherInflowM3', 'groundwaterInflowM3', 'externalInflowM3'):
        value = totals[key]
        (incoming if value >= 0 else outgoing).append(abs(value))
    value = totals['outflowM3']
    (outgoing if value >= 0 else incoming).append(abs(value))
    total_in, total_out = math.fsum(incoming), math.fsum(outgoing)
    residual = total_in - total_out
    scale = total_in if total_in > 0 else total_out
    require(all(math.isfinite(v) for v in (total_in, total_out, residual))
            and total_in >= 0 and total_out >= 0, 'NETWORK_CONTINUITY_INVALID')
    # EPA 보고값은 1ft³ 미만 잔차를 TINY로 줄이므로 원 체적으로 별도 판정한다.
    return {'method': 'UNSUPPRESSED_NATIVE_VOLUME_BALANCE', 'totalInM3': total_in,
            'totalOutIncludingStorageM3': total_out, 'residualM3': residual,
            'continuityPercent': 100 * residual / scale if scale else 0.,
            'absoluteToleranceM3': 1e-8, 'allowedResidualM3': max(1e-8, .01 * scale)}


def assess(complete, runoff_percent, routing_percent, has_catchments, convergence, balance):
    require(all(math.isfinite(v) for v in (runoff_percent, routing_percent)),
            'NETWORK_CONTINUITY_INVALID')
    failures = []
    if not complete:
        failures.append('EVALUATION_INCOMPLETE')
    if abs(routing_percent) > 1:
        failures.append('ROUTING_CONTINUITY_EXCEEDED')
    if abs(balance['residualM3']) > balance['allowedResidualM3']:
        failures.append('ROUTING_VOLUME_RESIDUAL_EXCEEDED')
    if has_catchments and abs(runoff_percent) > 1:
        failures.append('RUNOFF_CONTINUITY_EXCEEDED')
    if convergence['routingSteps'] == 0:
        failures.append('NO_ROUTING_STEPS')
    if convergence['nonConvergedSteps']:
        failures.append('ROUTING_NONCONVERGED')
    return {'policyVersion': POLICY, 'continuityLimitPercent': 1,
            'routingBalance': balance,
            'allowedNonConvergedSteps': 0, 'failureReasons': failures,
            'status': 'FAILED' if failures else 'PASSED'}
