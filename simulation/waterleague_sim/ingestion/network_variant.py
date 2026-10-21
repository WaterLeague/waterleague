"""공개 관망의 수치 설정만 변경하는 불변 파생 입력."""
import json
import math
import re

from waterleague_sim.engine.flood_errors import require
from waterleague_sim.ingestion.published_network import digest, records, execution_input

OPTIONS = frozenset(('SURCHARGE_METHOD', 'ROUTING_STEP', 'MINIMUM_STEP', 'MAX_TRIALS'))
HYDROLOGY_OPTIONS = frozenset(('WET_STEP', 'DRY_STEP'))


def hydraulic_input_hash(raw, *, hydrology=False):
    sections = records(raw)[1]
    canonical = {}
    for section, rows in sections.items():
        values = []
        for row in rows:
            tokens = row['tokens'][:]
            if section == 'OPTIONS' and tokens[0].upper() in (OPTIONS | (HYDROLOGY_OPTIONS if hydrology else frozenset())):
                continue
            if section == 'LID_USAGE' and len(tokens) >= 9:
                tokens[8] = '*'
            values.append(tokens)
        canonical[section] = values
    return digest(json.dumps(canonical, ensure_ascii=False, sort_keys=True,
                             separators=(',', ':'), allow_nan=False).encode())


def derive(raw, profile):
    return _derive(raw, profile, execution_input)


def derive_compiled(raw, profile):
    """시설 컴파일 이후 입력의 출력 경로는 바꾸지 않고 수치 옵션만 파생."""
    text, sections = records(raw)
    require(not any(sections.get(name) for name in ('FILES', 'TEMPERATURE', 'EVENTS')),
            'NETWORK_VARIANT_EXTERNAL_FILE_REJECTED')
    for section, rows in sections.items():
        for row in rows:
            tokens = row['tokens']
            require(not (section in ('TIMESERIES', 'RAINGAGES', 'EVAPORATION', 'REPORT')
                         and 'FILE' in [t.upper() for t in tokens])
                and not (section == 'LID_USAGE' and len(tokens) >= 9 and tokens[8] != '*'),
                'NETWORK_VARIANT_EXTERNAL_FILE_REJECTED')
    result, metadata = _derive(raw, profile, lambda _: (text, None))
    metadata['classification'] = 'NUMERICAL_VARIANT_OF_COMPILED_INPUT'
    return result, metadata


def _derive(raw, profile, prepare):
    require(isinstance(profile, dict) and set(profile) == {'id', 'options'}
            and isinstance(profile['id'], str)
            and re.fullmatch(r'[a-z][a-z0-9-]{0,63}', profile['id']), 'NETWORK_VARIANT_INVALID')
    options = profile['options']
    require(isinstance(options, dict) and options and set(options) <= OPTIONS | HYDROLOGY_OPTIONS,
            'NETWORK_VARIANT_OPTION_REJECTED')
    hydrology = bool(HYDROLOGY_OPTIONS.intersection(options))
    require(not hydrology or HYDROLOGY_OPTIONS <= options.keys(), 'NETWORK_VARIANT_HYDROLOGY_PAIR_REQUIRED')
    for key, value in options.items():
        if key == 'SURCHARGE_METHOD':
            require(value in ('EXTRAN', 'SLOT'), 'NETWORK_VARIANT_SURCHARGE_INVALID')
        elif key in HYDROLOGY_OPTIONS:
            require(type(value) is int and 1 <= value <= 300, 'NETWORK_VARIANT_HYDROLOGY_STEP_INVALID')
        elif key == 'MAX_TRIALS':
            require(type(value) is int and 8 <= value <= 2000, 'NETWORK_VARIANT_TRIALS_INVALID')
        else:
            require(type(value) in (int, float) and math.isfinite(value) and .001 <= value <= 60,
                    'NETWORK_VARIANT_STEP_INVALID')
    if 'ROUTING_STEP' in options and 'MINIMUM_STEP' in options:
        require(options['MINIMUM_STEP'] <= options['ROUTING_STEP'], 'NETWORK_VARIANT_MINIMUM_EXCEEDS_MAXIMUM')
    require(not hydrology or options['WET_STEP'] <= options['DRY_STEP'], 'NETWORK_VARIANT_WET_EXCEEDS_DRY')
    text, output_changes = prepare(raw)
    _, sections = records(text.encode())
    entries = {row['tokens'][0].upper(): row for row in sections['OPTIONS']}
    require(all(len(row['tokens']) == 2 for row in entries.values()), 'NETWORK_VARIANT_OPTION_FORMAT')
    lines, changes = text.splitlines(keepends=True), []
    appended = []
    for key, value in sorted(options.items()):
        token = f'{value//3600:02}:{value//60%60:02}:{value%60:02}' if key in HYDROLOGY_OPTIONS else str(value)
        row = entries.get(key)
        if row:
            source = lines[row['line'] - 1]
            match = re.match(r'(\s*\S+\s+)(\S+)', source)
            require(match is not None, 'NETWORK_VARIANT_OPTION_FORMAT')
            lines[row['line'] - 1] = source[:match.start(2)] + token + source[match.end(2):]
            before, source_line = row['tokens'][1], row['line']
        else:
            appended.append(key + ' ' + token)
            before, source_line = None, None
        changes.append({'option': key, 'sourceLine': source_line, 'before': before, 'after': token})
    if appended:
        marker = next(i for i, line in enumerate(lines)
                      if re.fullmatch(r'\s*\[OPTIONS\]\s*(?:;.*)?', line.rstrip('\r\n'), re.IGNORECASE))
        ending = '\r\n' if lines[marker].endswith('\r\n') else '\n'
        lines[marker + 1:marker + 1] = [line + ending for line in appended]
    derived = ''.join(lines).encode()
    # 기존 파생 입력의 해시는 보존하고, 명시한 수문 간격 변경만 새 비교 범위에서 제외한다.
    source_hash, derived_hash = (hydraulic_input_hash(value, hydrology=hydrology) for value in (raw, derived))
    require(source_hash == derived_hash, 'NETWORK_VARIANT_HYDRAULIC_INPUT_CHANGED')
    original_method = entries.get('SURCHARGE_METHOD', {'tokens': ['', 'EXTRAN']})['tokens'][1].upper()
    method = options.get('SURCHARGE_METHOD', original_method)
    return derived, {'schemaVersion': 1, 'profile': profile,
        'classification': 'NUMERICAL_VARIANT_OF_PUBLISHED_RESEARCH_INPUT',
        'originalSha256': digest(raw), 'derivedSha256': digest(derived),
        'hydraulicInputSha256': source_hash, 'hydraulicInputValuesUnchanged': True,
        'originalSurchargeMethod': original_method, 'derivedSurchargeMethod': method,
        'hydraulicApproximationChanged': method != original_method,
        'reportOutputTransformation': output_changes, 'numericalChanges': changes,
        'rankingEligible': False, 'historicalReconstructionEligible': False}
