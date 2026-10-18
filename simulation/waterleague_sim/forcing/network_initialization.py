"""보관 관측을 전체 기간이 명시된 연결 관망의 강우·증발 입력으로 변환."""
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
import math
from pathlib import Path
import re

from waterleague_sim.engine.flood_errors import require
from waterleague_sim.engine.swmm import ROOT
from waterleague_sim.forcing.antecedent_archive import read_antecedent
from waterleague_sim.forcing.observed_rainfall import digest, read_station, utc
from waterleague_sim.forcing.reference_evaporation import read_reference
from waterleague_sim.ingestion.published_network import records

METHOD = 'OBSERVED_NETWORK_ANTECEDENT_CONTINUOUS_V1'
PREFIX = 'WL_INIT_'


def _date(date, time):
    for form in ('%m/%d/%Y %H:%M:%S', '%m/%d/%Y %H:%M'):
        try:
            return datetime.strptime(date + ' ' + time, form).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    require(False, 'NETWORK_INITIALIZATION_EXPLICIT_TIME_REQUIRED')


def _external_series(sections, model, start, end):
    used = set()
    for row in sections.get('INFLOWS', []):
        tokens = row['tokens']
        require(len(tokens) >= 3, 'NETWORK_INITIALIZATION_INFLOW_INVALID')
        if tokens[2] not in ('*', '""'):
            used.add(tokens[2].upper())
    for row in sections.get('OUTFALLS', []):
        tokens = row['tokens']
        require(len(tokens) >= 3, 'NETWORK_INITIALIZATION_OUTFALL_INVALID')
        if tokens[2].upper() == 'TIMESERIES':
            require(len(tokens) >= 4, 'NETWORK_INITIALIZATION_OUTFALL_INVALID')
            used.add(tokens[3].upper())
    for row in sections.get('CONTROLS', []):
        tokens = [v.upper() for v in row['tokens']]
        if 'TIMESERIES' in tokens:
            i = tokens.index('TIMESERIES')
            require(i + 1 < len(tokens), 'NETWORK_INITIALIZATION_CONTROL_INVALID')
            used.add(tokens[i + 1])
    evidence = model.get('externalTimeSeries', {})
    require(isinstance(evidence, dict) and all(isinstance(k, str) for k in evidence),
            'NETWORK_INITIALIZATION_EXTERNAL_SERIES_EVIDENCE_REQUIRED')
    require(len({k.upper() for k in evidence}) == len(evidence),
            'NETWORK_INITIALIZATION_EXTERNAL_SERIES_EVIDENCE_REQUIRED')
    evidence = {k.upper(): v for k, v in evidence.items()}
    verified = []
    for name in sorted(used):
        source = evidence.get(name)
        require(isinstance(source, dict) and source.get('evidence')
                and type(source.get('maximumIntervalSeconds')) in (int, float)
                and math.isfinite(source['maximumIntervalSeconds']) and source['maximumIntervalSeconds'] > 0,
                'NETWORK_INITIALIZATION_EXTERNAL_SERIES_EVIDENCE_REQUIRED')
        times = []
        for row in sections.get('TIMESERIES', []):
            t = row['tokens']
            if t[0].upper() != name:
                continue
            require(len(t) == 4, 'NETWORK_INITIALIZATION_EXTERNAL_SERIES_ABSOLUTE_TIME_REQUIRED')
            at = _date(t[1], t[2])
            try:
                value = float(t[3])
            except ValueError:
                require(False, 'NETWORK_INITIALIZATION_EXTERNAL_SERIES_INVALID')
            require(math.isfinite(value) and (not times or 0 < (at-times[-1]).total_seconds()
                    <= source['maximumIntervalSeconds']), 'NETWORK_INITIALIZATION_EXTERNAL_SERIES_GAP')
            times.append(at)
        require(times and times[0] <= start and times[-1] >= end,
                'NETWORK_INITIALIZATION_EXTERNAL_SERIES_COVERAGE_INCOMPLETE')
        verified.append({'id': name, 'startUtc': times[0].isoformat(), 'endUtc': times[-1].isoformat(),
                         **deepcopy(source)})
    return verified


def _append(lines, section, rows):
    marker = next((i for i, line in enumerate(lines) if line.split(';', 1)[0].strip().upper()
                   == '[' + section + ']'), None)
    if marker is None:
        lines.extend(['', '[' + section + ']', *rows])
    else:
        lines[marker + 1:marker + 1] = rows


@dataclass
class InitializedNetwork:
    model: dict
    summary: dict
    source_files: dict

    def archive(self, directory):
        directory.mkdir(parents=True)
        for name, raw in self.source_files.items():
            path = directory / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        (directory / 'forcing-summary.json').write_text(
            json.dumps(self.summary, ensure_ascii=False, allow_nan=False, indent=2) + '\n')


def prepare_initialized_network(model, specification, initialization, *, root=ROOT):
    require(isinstance(initialization, dict) and initialization.get('schemaVersion') == 1
            and initialization.get('method') == METHOD and type(initialization.get('days')) is int
            and initialization['days'] in (7, 14, 28) and initialization.get('evidence'),
            'NETWORK_INITIALIZATION_INVALID')
    require(isinstance(specification, dict) and specification.get('schemaVersion') == 1
            and specification.get('assignmentEvidence'), 'NETWORK_OBSERVATION_INVALID')
    evaluation_start, end = utc(specification.get('startUtc')), utc(specification.get('endUtc'))
    warmup_seconds = initialization['days'] * 86400
    start = evaluation_start - timedelta(seconds=warmup_seconds)
    evaluation_seconds = (end-evaluation_start).total_seconds()
    require(0 < evaluation_seconds <= 86400 and evaluation_seconds % 60 == 0
            and start.second == start.microsecond == 0, 'NETWORK_INITIALIZATION_WINDOW_INVALID')
    require(isinstance(model, dict) and model.get('timeZone') == 'UTC'
            and isinstance(model.get('inputText'), str), 'NETWORK_INITIALIZATION_MODEL_INVALID')
    if 'startUtc' in model or 'durationSeconds' in model:
        require(utc(model.get('startUtc')) == start
                and model.get('durationSeconds') == warmup_seconds + evaluation_seconds,
                'NETWORK_INITIALIZATION_MODEL_CLOCK_MISMATCH')
    original = model['inputText'].encode()
    text, sections = records(original)
    options = {r['tokens'][0].upper(): r['tokens'][1] for r in sections.get('OPTIONS', [])
               if len(r['tokens']) == 2}
    require(all(k in options for k in ('START_DATE', 'START_TIME', 'END_DATE', 'END_TIME',
                                      'REPORT_START_DATE', 'REPORT_START_TIME')),
            'NETWORK_INITIALIZATION_EXPLICIT_TIME_REQUIRED')
    require(_date(options['START_DATE'], options['START_TIME']) == start
            and _date(options['REPORT_START_DATE'], options['REPORT_START_TIME']) == start
            and _date(options['END_DATE'], options['END_TIME']) == end + timedelta(seconds=1),
            'NETWORK_INITIALIZATION_MODEL_CLOCK_MISMATCH')
    require(options.get('FLOW_UNITS', '').upper() == 'CMS' and options.get('FLOW_ROUTING', '').upper() == 'DYNWAVE'
            and options.get('WET_STEP') == options.get('DRY_STEP') == '00:00:01',
            'NETWORK_INITIALIZATION_SECOND_HYDROLOGY_REQUIRED')
    for section in ('FILES', 'TEMPERATURE', 'EVENTS', 'SNOWPACKS', 'AQUIFERS', 'GROUNDWATER',
                    'GWF', 'RDII', 'HYDROGRAPHS', 'ADJUSTMENTS'):
        require(not sections.get(section), 'NETWORK_INITIALIZATION_UNSUPPORTED_FORCING')
    require(not any(PREFIX in token.upper() for rows in sections.values() for row in rows for token in row['tokens']),
            'NETWORK_INITIALIZATION_RESERVED_NAME')
    external = _external_series(sections, model, start, end)
    modifiers = {}
    for row in sections.get('EVAPORATION', []):
        tokens = row['tokens']
        key = tokens[0].upper()
        if key in ('RECOVERY', 'DRY_ONLY'):
            require(len(tokens) == 2 and key not in modifiers
                    and (key != 'DRY_ONLY' or tokens[1].upper() in ('YES', 'NO')),
                    'NETWORK_INITIALIZATION_EVAPORATION_CONTROL_INVALID')
            modifiers[key] = tokens[1]
    assignments = specification.get('stationByCatchment')
    catchments = {r['tokens'][0]: r for r in sections.get('SUBCATCHMENTS', [])}
    require(len({k.upper() for k in catchments}) == len(sections.get('SUBCATCHMENTS', [])),
            'NETWORK_INITIALIZATION_DUPLICATE_CATCHMENT')
    catchment_areas = {}
    for name, row in catchments.items():
        require(len(row['tokens']) >= 8, 'NETWORK_INITIALIZATION_CATCHMENT_INVALID')
        try:
            area = float(row['tokens'][3])*10000
        except ValueError:
            require(False, 'NETWORK_INITIALIZATION_CATCHMENT_INVALID')
        require(math.isfinite(area) and area > 0, 'NETWORK_INITIALIZATION_CATCHMENT_INVALID')
        catchment_areas[name] = area
    require(isinstance(assignments, dict) and assignments and set(assignments) == set(catchments)
            and all(isinstance(s, str) and re.fullmatch(r'\d{1,5}', s) for s in assignments.values()),
            'NETWORK_INITIALIZATION_ASSIGNMENT_INCOMPLETE')
    references, prior_references = specification.get('stations'), initialization.get('stations')
    require(isinstance(references, list) and isinstance(prior_references, list)
            and 0 < len(references) == len(prior_references) <= 100
            and all(isinstance(v, dict) for v in references + prior_references),
            'NETWORK_INITIALIZATION_SOURCES_REQUIRED')
    rainfall, prior, files = {}, {}, {}
    count = int(evaluation_seconds) // 60
    for reference in references:
        data, sources = read_station(reference, root)
        sid = data['stationId']
        offset = (evaluation_start-utc(data['start'])).total_seconds()
        require(sid not in rainfall and offset >= 0 and offset % 60 == 0 and utc(data['end']) >= end,
                'NETWORK_INITIALIZATION_RAIN_COVERAGE_INCOMPLETE')
        rainfall[sid] = data['depthsMm'][int(offset//60):int(offset//60)+count]
        files.update(sources)
    for reference in prior_references:
        data, pet, sources, summary = read_antecedent(reference, root)
        sid = data['stationId']
        offset = (start-utc(data['start'])).total_seconds()
        require(sid not in prior and offset >= 0 and offset % 60 == 0
                and utc(data['end']) == evaluation_start, 'NETWORK_INITIALIZATION_ANTECEDENT_BINDING_INVALID')
        prior[sid] = {'depths': data['depthsMm'][int(offset//60):],
                      'pet': pet['ratesMmDay'][int(offset//60):], 'reference': reference, 'summary': summary}
        files.update(sources)
    require(set(rainfall) == set(prior) == set(assignments.values()), 'NETWORK_INITIALIZATION_ASSIGNMENT_INCOMPLETE')
    weather_reference = initialization.get('weatherReference')
    require(weather_reference in prior_references, 'NETWORK_INITIALIZATION_WEATHER_BINDING_INVALID')
    prior_weather = next(v for v in prior.values() if v['reference'] == weather_reference)
    weather, weather_files, weather_code = read_reference(specification.get('evaporationReference'), root)
    offset = (evaluation_start-utc(weather['start'])).total_seconds()
    require(offset >= 0 and offset % 60 == 0 and utc(weather['end']) >= end,
            'NETWORK_INITIALIZATION_WEATHER_COVERAGE_INCOMPLETE')
    evaporation = prior_weather['pet'] + weather['ratesMmDay'][int(offset//60):int(offset//60)+count]
    files.update(weather_files)
    series, gages, totals = [], [], []
    for sid in sorted(rainfall):
        values = prior[sid]['depths'] + rainfall[sid]
        require(len(values) == len(evaporation) == warmup_seconds//60+count,
                'NETWORK_INITIALIZATION_LENGTH_MISMATCH')
        gauge, name = PREFIX + 'G' + sid, PREFIX + 'R' + sid
        gages.append(f'{gauge} INTENSITY 0:01 1.0 TIMESERIES {name}')
        # EPA 강우계의 +1초 탐색을 상쇄하여 다음 분 강우의 조기 투입을 방지한다.
        for index, value in enumerate(values):
            # 1분 강우계의 빈 구간은 0이므로 연속 관측 0만 생략하며 양수 구간은 모두 보존한다.
            if index and value == values[index-1] == 0:
                continue
            at = start + timedelta(minutes=index, seconds=1)
            rate = Decimal(str(value)) * 60
            series.append(f'{name} {at:%m/%d/%Y} {at:%H:%M:%S} {rate}')
        at = end + timedelta(seconds=1)
        series.append(f'{name} {at:%m/%d/%Y} {at:%H:%M:%S} 0')
        area = math.fsum(catchment_areas[k] for k, s in assignments.items() if s == sid)
        totals.append({'stationId': sid, 'catchmentAreaM2': area,
            'warmupDepthMm': math.fsum(prior[sid]['depths']), 'evaluationDepthMm': math.fsum(rainfall[sid]),
            'grossEvaluationRainfallM3': math.fsum(rainfall[sid])*area/1000})
    previous = None
    for index, value in enumerate(evaporation):
        if value != previous:
            at = start + timedelta(minutes=index)
            series.append(f'{PREFIX}PET {at:%m/%d/%Y} {at:%H:%M:%S} {value}')
        previous = value
    series.append(f'{PREFIX}PET {end:%m/%d/%Y} {end:%H:%M:%S} {previous}')
    lines, section = [], ''
    for line in text.splitlines():
        tokens = line.split(';', 1)[0].split()
        if tokens and tokens[0].startswith('['):
            section = tokens[0].strip('[]').upper()
        if section in ('RAINGAGES', 'EVAPORATION'):
            continue
        if tokens and section == 'SUBCATCHMENTS' and tokens[0] in assignments:
            match = re.match(r'(\s*\S+\s+)(\S+)', line)
            line = line[:match.start(2)] + PREFIX + 'G' + assignments[tokens[0]] + line[match.end(2):]
        lines.append(line)
    _append(lines, 'RAINGAGES', gages)
    # 관측 잠재 증발률만 바꾸며 원 모형의 침투 회복·무강우 증발 제어는 유지한다.
    _append(lines, 'EVAPORATION', ['TIMESERIES ' + PREFIX + 'PET',
                                  *[key+' '+value for key, value in modifiers.items()]])
    _append(lines, 'TIMESERIES', series)
    derived = ('\n'.join(lines)+'\n').encode()
    require(len(derived) <= 2_000_000, 'NETWORK_INITIALIZATION_INPUT_TOO_LARGE')
    summary = {'schemaVersion': 1, 'method': METHOD, 'startUtc': start.isoformat(),
        'evaluationStartUtc': evaluation_start.isoformat(), 'endUtc': end.isoformat(),
        'warmupSeconds': warmup_seconds, 'evaluationSeconds': int(evaluation_seconds),
        'originalSha256': digest(original), 'derivedSha256': digest(derived),
        'specification': deepcopy(specification), 'initialization': deepcopy(initialization),
        'stations': totals, 'antecedent': [v['summary'] for v in prior.values()],
        'evaporation': {'method': weather['method'], 'evaluationTimePolicy': weather['timePolicy'],
            'antecedentTimePolicy': 'PREVIOUS_COMPLETED_DAY_HELD_OVER_NEXT_DAY',
            'preservedInputControls': modifiers,
            'assumptions': weather['assumptions'], 'reconstructionCode': weather_code,
            'warmupPotentialDepthMm': math.fsum(evaporation[:warmup_seconds//60])/1440,
            'evaluationPotentialDepthMm': math.fsum(evaporation[warmup_seconds//60:])/1440},
        'externalTimeSeries': external, 'rankingEligible': False,
        'limitations': ['분 강우의 구간 일정 강도와 관측소→집수구역 공간 배정 근사',
            '기준 잔디 증발산의 시설/관망 전용은 표면별 보정 없는 잠재 증발 입력',
            '초기 시드는 관측 수분이 아니며 시설이 선행 기간에 존재한 조건',
            '총 집수 면적 강우와 덮개 시설 직접 강우 제외의 차이 보존; 전체 유역 수지 아님'],
        'sourceFiles': {name: digest(body) for name, body in files.items()},
        'adapterSha256': digest(Path(__file__).read_bytes())}
    return InitializedNetwork(deepcopy(model) | {'inputText': derived.decode()}, summary, files)
