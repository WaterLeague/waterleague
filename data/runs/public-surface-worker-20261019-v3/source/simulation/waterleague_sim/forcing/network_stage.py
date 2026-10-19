"""시간별 경계수위를 원본 방류구의 EPA 시계열 입력으로 연결."""
from dataclasses import dataclass
import hashlib
from pathlib import Path

from waterleague_sim.engine.flood_errors import require
from waterleague_sim.forcing.stage import StageSeries, require_network_start, source_hash as stage_source_hash, utc


@dataclass
class NetworkStageInput:
    text: str
    series: dict
    summary: dict


def prepare_network_stage(model, *, evaluation_seconds=None):
    text = model.get('inputText')
    require(isinstance(text, str), 'NETWORK_INPUT_INVALID')
    specifications = model.get('outfallStageBoundaries', {})
    require(isinstance(specifications, dict) and len(specifications) <= 1000,
            'NETWORK_STAGE_SPECIFICATION_INVALID')
    if not specifications:
        return NetworkStageInput(text, {}, {})
    require(all(isinstance(key, str) and key and isinstance(value, dict)
                for key, value in specifications.items()), 'NETWORK_STAGE_SPECIFICATION_INVALID')
    series = {key: StageSeries(spec, model, momentum_policy='SWMM_DYNAMIC_WAVE')
              for key, spec in specifications.items()}
    duration = model['durationSeconds']
    require(type(duration) is int and (evaluation_seconds is None or evaluation_seconds == duration),
            'NETWORK_STAGE_WINDOW_MISMATCH')
    require_network_start(model, utc(model['startUtc']))
    identifiers = {key.upper(): key for key in series}
    require(len(identifiers) == len(series), 'NETWORK_STAGE_DUPLICATE_OUTFALL')
    ports = model.get('ports', [])
    require(not set(identifiers).intersection(str(row.get('outfall', '')).upper() for row in ports),
            'NETWORK_STAGE_EXCHANGE_CONFLICT')
    lines = text.splitlines()
    existing_series, outfalls, options, section = set(), {}, {}, ''
    for index, line in enumerate(lines):
        fields = line.split(';', 1)[0].split()
        if fields and fields[0].startswith('['):
            section = fields[0].upper()
        elif fields:
            if section == '[TIMESERIES]':
                existing_series.add(fields[0].upper())
            elif section == '[OUTFALLS]':
                require(fields[0].upper() not in outfalls, 'NETWORK_STAGE_DUPLICATE_OUTFALL')
                outfalls[fields[0].upper()] = (index, fields)
            elif section == '[OPTIONS]' and len(fields) == 2:
                options[fields[0].upper()] = fields[1].upper()
    require(set(identifiers) <= set(outfalls), 'NETWORK_STAGE_OUTFALL_REQUIRED')
    units = options.get('FLOW_UNITS')
    require(units in ('CMS', 'CFS'), 'NETWORK_STAGE_UNITS_UNSUPPORTED')
    length_scale = .3048 if units == 'CFS' else 1.
    added, summaries = [], {}
    for upper, key in sorted(identifiers.items()):
        index, fields = outfalls[upper]
        original_line = lines[index]
        require(len(fields) >= 3 and fields[2].upper() in ('FIXED', 'FREE', 'NORMAL'),
                'NETWORK_STAGE_EXISTING_SERIES_CONFLICT')
        tail_start = 4 if fields[2].upper() == 'FIXED' else 3
        require(tail_start <= len(fields) <= tail_start + 2, 'NETWORK_STAGE_OUTFALL_INVALID')
        tail = fields[tail_start:]
        require(not tail or tail[0].upper() in ('YES', 'NO'), 'NETWORK_STAGE_FLAP_INVALID')
        name = 'WL_STAGE_' + hashlib.sha256(key.encode()).hexdigest()[:20]
        require(name.upper() not in existing_series, 'NETWORK_STAGE_SERIES_COLLISION')
        existing_series.add(name.upper())
        comment = lines[index].partition(';')[2]
        lines[index] = ' '.join([fields[0], fields[1], 'TIMESERIES', name, *tail])
        if comment:
            lines[index] += ' ;' + comment
        for row in specifications[key]['samples']:
            instant = utc(row['timeUtc'])
            # EPA의 시:분:초 구문은 정수 초만 읽으므로 소수 시각은 십진 시간으로 기록한다.
            hours = instant.hour + (instant.minute * 60 + instant.second + instant.microsecond / 1e6) / 3600
            added.append(f"{name} {instant:%m/%d/%Y} {hours:.17g} {row['stageM'] / length_scale:.17g}")
        summaries[key] = series[key].summary | {'nativeSeriesId': name, 'nativeLengthUnit': 'ft' if units == 'CFS' else 'm',
            'originalOutfallLine': original_line, 'appliedOutfallLine': lines[index],
            'headInterpretation': 'WATER_SURFACE_ELEVATION_NOT_DEPTH',
            'nativeInterpolation': 'EPA_TIMESERIES_LINEAR_INTERNAL_ROUTING_TIME'}
    output = '\n'.join(lines) + '\n[TIMESERIES]\n' + '\n'.join(added) + '\n'
    return NetworkStageInput(output, series, {'outfalls': summaries,
        'originalInputSha256': hashlib.sha256(text.encode()).hexdigest(),
        'appliedInputSha256': hashlib.sha256(output.encode()).hexdigest(),
        'adapterSha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'stageAdapterSha256': stage_source_hash(), 'rankingEligible': False})
