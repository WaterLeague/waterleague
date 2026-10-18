"""시설 시드·선행 기간 이외의 조건을 고정한 연결 상태 비교."""
from copy import deepcopy
from datetime import datetime, timedelta
import json
from pathlib import Path

from .coupled_adapter import engine_signature, file_digest, read_coupled_record
from .exception import require
from .values import digest

SEEDED_TYPES = frozenset(('BIORETENTION', 'INFILTRATION_TRENCH', 'RAINWATER_CISTERN'))


def seeded_placements(model):
    placements = model['connectedFacilityDesign']['placements']
    require(all(row['facilityType'] in SEEDED_TYPES or (
        row['facilityType'] == 'VEGETATIVE_SWALE' and row['initialSaturationPercent'] == 0)
        for row in placements), 'INITIALIZATION_STUDY_SEED_NOT_APPLICABLE')
    return [row for row in placements if row['facilityType'] in SEEDED_TYPES]


def fixed_input(model):
    value = deepcopy(model)
    initialization = value['initialization']
    days = initialization.pop('days')
    require(type(days) is int and days in (7, 14, 28), 'INITIALIZATION_STUDY_PERIOD_INVALID')
    start = datetime.fromisoformat(value['observedRainfall']['startUtc']) - timedelta(days=days)
    require(start.utcoffset() == timedelta(0), 'INITIALIZATION_STUDY_CLOCK_INVALID')
    expected = {key: start.strftime(fmt) for key, fmt in (
        ('START_DATE', '%m/%d/%Y'), ('START_TIME', '%H:%M:%S'),
        ('REPORT_START_DATE', '%m/%d/%Y'), ('REPORT_START_TIME', '%H:%M:%S'))}
    lines, seen, section = [], set(), ''
    for line in value['network']['inputText'].splitlines():
        tokens = line.split(';', 1)[0].split()
        if tokens and tokens[0].startswith('['):
            section = tokens[0].upper()
        if section == '[OPTIONS]' and tokens and tokens[0].upper() in expected:
            key = tokens[0].upper()
            require(key not in seen and tokens == [key, expected[key]], 'INITIALIZATION_STUDY_CLOCK_INVALID')
            seen.add(key)
            line = key + ' PERIOD_DEPENDENT'
        lines.append(line)
    require(seen == set(expected), 'INITIALIZATION_STUDY_CLOCK_INVALID')
    value['network']['inputText'] = '\n'.join(lines)
    placements = seeded_placements(value)
    require(placements and all(type(row['initialSaturationPercent']) in (int, float)
        and row['initialSaturationPercent'] in (0, 100) for row in placements),
        'INITIALIZATION_STUDY_SEED_INVALID')
    require(len({row['initialSaturationPercent'] for row in placements}) == 1,
            'INITIALIZATION_STUDY_SEED_INVALID')
    for row in placements:
        row['initialSaturationPercent'] = 'VARIED_LID_SEED'
    step = value.pop('maximumExchangeMilliseconds')
    require(type(step) is int and 0 < step <= 60_000
            and value['surface'].pop('maxStepSeconds') * 1000 == step,
            'INITIALIZATION_STUDY_STEP_INVALID')
    return value


def summarize_case(directory):
    directory = Path(directory)
    def read(name):
        return json.loads((directory/name).read_bytes())
    model, result = read('coupled-input.json'), read('coupled-result.json')
    network, surface = read('network/network-result.json'), read('surface/surface-result.json')
    common = fixed_input(model)
    context = {'scopeId': 'COUPLED_INITIALIZATION_STUDY', 'modelGrade': 'DRAFT',
        'evidenceClass': 'NUMERICAL_TEST_ONLY', 'comparisonKind': 'CURRENT',
        'effectAreaId': 'EXPLICIT_REFERENCE_DOMAIN', 'scenarioSnapshotSha256': digest(common),
        'forcingSha256': digest([model['observedRainfall'], model['initialization']]),
        'engineSha256': engine_signature(network, surface, result),
        'metricSpecificationSha256': result['evaluationMetrics']['specificationSha256']}
    record = read_coupled_record(directory, file_digest(directory/'coupled-result.json'), context)
    comparable = deepcopy(result)
    comparable['surfaceNumericalConfiguration']['configuredMaximumStepSeconds'] = 'STUDY_VARIABLE'
    design = result['connectedFacilities']['design']
    comparable_engine = digest({'engineSha256': engine_signature(network, surface, comparable),
        'compilerSha256': design['compilerSha256'], 'catalogSha256': design['catalogSha256']})
    origin = read('evaluation-initial-state.json')
    ledger = result['initialization']['evaluationLedger']
    values = {'initial.networkStorageM3': origin['network']['totals']['storageM3'],
        'initial.surfaceStorageM3': origin['surface']['surface']['storageM3'],
        **{'evaluation.' + k: v for k, v in record['raw'].items()}}
    for row in origin['network']['facilities']:
        for key in ('soilMoisture', 'surfaceDepthMm', 'storageDepthMm', 'finalStorageM3'):
            values[f'initial.facility.{row["subcatchmentId"]}.{row["swmmId"]}.{key}'] = row[key]
    return {'status': record['numericalStatus'], 'complete': record['complete'],
        'warmupDays': model['initialization']['days'],
        'initialSaturationPercent': seeded_placements(model)[0]['initialSaturationPercent'],
        'maximumExchangeMilliseconds': model['maximumExchangeMilliseconds'],
        'fixedInputSha256': digest(common), 'engineSha256': context['engineSha256'],
        'comparableEngineSha256': comparable_engine,
        'inputSha256': record['inputSha256'], 'resultSha256': record['resultSha256'],
        'observables': values, 'evaluationLedger': ledger,
        'initialSurfaceInfiltrationState': origin['surface']['infiltration'],
        'networkConvergence': result['networkConvergence'],
        'dryExchangeRoundoff': result['dryExchangeRoundoff']}


def difference(left, right, *, variable):
    require(variable in ('warmupDays', 'initialSaturationPercent', 'maximumExchangeMilliseconds'),
            'INITIALIZATION_STUDY_VARIABLE_INVALID')
    require(left['fixedInputSha256'] == right['fixedInputSha256'], 'INITIALIZATION_STUDY_INPUT_MISMATCH')
    require(left['comparableEngineSha256'] == right['comparableEngineSha256'],
            'INITIALIZATION_STUDY_ENGINE_MISMATCH')
    for key in ('warmupDays', 'initialSaturationPercent', 'maximumExchangeMilliseconds'):
        require(key == variable or left[key] == right[key], 'INITIALIZATION_STUDY_CONFOUNDED_COMPARISON')
    if variable != 'maximumExchangeMilliseconds':
        require(left['engineSha256'] == right['engineSha256'], 'INITIALIZATION_STUDY_ENGINE_MISMATCH')
    if any(row['status'] != 'PASSED' or not row['complete'] for row in (left, right)):
        return {'status': 'WITHHELD', 'difference': None, 'reason': 'FAILED_OR_INCOMPLETE_RUN'}
    a, b = left['observables'], right['observables']
    require(a.keys() == b.keys(), 'INITIALIZATION_STUDY_STATE_MISMATCH')
    require(all((a[key] is None) == (b[key] is None) for key in a), 'INITIALIZATION_STUDY_STATE_MISMATCH')
    return {'status': 'AVAILABLE', 'direction': 'LEFT_MINUS_RIGHT',
        'difference': {key: a[key]-b[key] if a[key] is not None and b[key] is not None else None for key in a}}
