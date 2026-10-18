"""공개 관망의 수치 설정만 변경하는 불변 파생 입력."""
import json
import math
import re

from waterleague_sim.engine.flood_errors import require
from waterleague_sim.ingestion.published_network import digest, records, execution_input

OPTIONS = frozenset(('SURCHARGE_METHOD', 'ROUTING_STEP', 'MINIMUM_STEP', 'MAX_TRIALS'))


def hydraulic_input_hash(raw):
    sections = records(raw)[1]
    canonical = {}
    for section, rows in sections.items():
        values = []
        for row in rows:
            tokens = row['tokens'][:]
            if section == 'OPTIONS' and tokens[0].upper() in OPTIONS:
                continue
            if section == 'LID_USAGE' and len(tokens) >= 9:
                tokens[8] = '*'
            values.append(tokens)
        canonical[section] = values
    return digest(json.dumps(canonical, ensure_ascii=False, sort_keys=True,
                             separators=(',', ':'), allow_nan=False).encode())


def derive(raw, profile):
    require(isinstance(profile, dict) and set(profile) == {'id', 'options'}
            and isinstance(profile['id'], str)
            and re.fullmatch(r'[a-z][a-z0-9-]{0,63}', profile['id']), 'NETWORK_VARIANT_INVALID')
    options = profile['options']
    require(isinstance(options, dict) and options and set(options) <= OPTIONS,
            'NETWORK_VARIANT_OPTION_REJECTED')
    for key, value in options.items():
        if key == 'SURCHARGE_METHOD':
            require(value in ('EXTRAN', 'SLOT'), 'NETWORK_VARIANT_SURCHARGE_INVALID')
        elif key == 'MAX_TRIALS':
            require(type(value) is int and 8 <= value <= 2000, 'NETWORK_VARIANT_TRIALS_INVALID')
        else:
            require(type(value) in (int, float) and math.isfinite(value) and .001 <= value <= 60,
                    'NETWORK_VARIANT_STEP_INVALID')
    if 'ROUTING_STEP' in options and 'MINIMUM_STEP' in options:
        require(options['MINIMUM_STEP'] <= options['ROUTING_STEP'], 'NETWORK_VARIANT_MINIMUM_EXCEEDS_MAXIMUM')
    text, output_changes = execution_input(raw)
    _, sections = records(text.encode())
    entries = {row['tokens'][0].upper(): row for row in sections['OPTIONS']}
    require(all(len(row['tokens']) == 2 for row in entries.values()), 'NETWORK_VARIANT_OPTION_FORMAT')
    lines, changes = text.splitlines(keepends=True), []
    appended = []
    for key, value in sorted(options.items()):
        token = str(value)
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
    source_hash, derived_hash = hydraulic_input_hash(raw), hydraulic_input_hash(derived)
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
