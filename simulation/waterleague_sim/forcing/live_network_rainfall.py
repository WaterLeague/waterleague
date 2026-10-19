"""직접 AWS 응답과 SWMM 집수 강우계의 명시적 결속. 기존 INP 보존."""
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
import math
from pathlib import Path
import re

from waterleague_sim.engine.flood_errors import require
from waterleague_sim.forcing.live_rainfall import read_live_station, sha
from waterleague_sim.forcing.network_initialization import _date, _append, _external_series
from waterleague_sim.forcing.observed_rainfall import utc, require_network_clock
from waterleague_sim.ingestion.published_network import records

METHOD = 'DIRECT_AWS_NETWORK_GAGES_V1'
PREFIX = 'WL_AWS_'
FACILITY_OBSERVER = 'DIRECT_RAIN_CONNECTED_FACILITY_V1'


def validate_facility_binding(model):
    require(not any(k in model for k in ('initialization', 'connectedStorageDesign', 'connectedPumpDesign')),
            'LIVE_NETWORK_DESIGN_BINDING_UNSUPPORTED')
    design = model.get('connectedFacilityDesign')
    if design is not None:
        require(not any(k in model for k in ('surfaceBasinDesign', 'networkNumericalProfile')),
                'LIVE_NETWORK_DESIGN_BINDING_UNSUPPORTED')
        from waterleague_sim.engine.connected_facilities import compile_design
        require(model.get('evaluationMetrics') is not None, 'COUPLED_FACILITY_METRICS_REQUIRED')
        compile_design(model['network']['inputText'].encode(), design)
        # 덮개형 RB가 제외한 덮개 강우를 우회시키는 지리 배정 전에는 물량 소실을 허용하지 않는다.
        require(all(row['facilityType'] in ('BIORETENTION', 'INFILTRATION_TRENCH', 'VEGETATIVE_SWALE')
                    for row in design['placements']), 'LIVE_FACILITY_COVER_RAIN_ROUTING_REQUIRED')


def validate_network(network, spec):
    require_network_clock(network, spec)
    start, end = utc(spec['startUtc']), utc(spec['endUtc'])
    require(0 < (end-start).total_seconds() <= 29*86400
            and start.second == end.second == start.microsecond == end.microsecond == 0,
            'LIVE_NETWORK_WINDOW_INVALID')
    if 'startUtc' in network or 'durationSeconds' in network:
        require(utc(network.get('startUtc')) == start
                and network.get('durationSeconds') == (end-start).total_seconds(), 'LIVE_NETWORK_CLOCK_INVALID')
    text, sections = records(network['inputText'].encode())
    option_rows = sections.get('OPTIONS', [])
    require(all(len(r['tokens']) == 2 for r in option_rows), 'LIVE_NETWORK_OPTIONS_INVALID')
    options = {r['tokens'][0].upper(): r['tokens'][1] for r in option_rows}
    require(len(options) == len(option_rows), 'LIVE_NETWORK_OPTIONS_INVALID')
    require(all(k in options for k in ('START_DATE', 'START_TIME', 'END_DATE', 'END_TIME',
                'REPORT_START_DATE', 'REPORT_START_TIME')), 'LIVE_NETWORK_CLOCK_INVALID')
    require(_date(options['REPORT_START_DATE'], options['REPORT_START_TIME']) == start
            and _date(options['END_DATE'], options['END_TIME']) == end+timedelta(seconds=1),
            'LIVE_NETWORK_CLOCK_INVALID')
    require(options.get('FLOW_UNITS', '').upper() == 'CMS'
            and options.get('FLOW_ROUTING', '').upper() == 'DYNWAVE'
            and options.get('WET_STEP') == options.get('DRY_STEP') == '00:00:01'
            and options.get('IGNORE_RAINFALL', 'NO').upper() == 'NO'
            and options.get('IGNORE_RUNOFF', 'NO').upper() == 'NO',
            'LIVE_NETWORK_SECOND_HYDROLOGY_REQUIRED')
    # 강우 수정·적설·지하수·LID의 별도 입력 결속 전에는 해당 조합을 개방하지 않는다.
    for section in ('FILES', 'TEMPERATURE', 'EVENTS', 'SNOWPACKS', 'AQUIFERS', 'GROUNDWATER',
                    'GWF', 'RDII', 'HYDROGRAPHS', 'ADJUSTMENTS', 'LID_USAGE'):
        require(not sections.get(section), 'LIVE_NETWORK_UNSUPPORTED_FORCING')
    require(not any(PREFIX in token.upper() for rows in sections.values() for row in rows
                    for token in row['tokens']), 'LIVE_NETWORK_RESERVED_NAME')
    require(not any('FILE' in [t.upper() for t in row['tokens']]
                    for section in ('TIMESERIES', 'RAINGAGES', 'EVAPORATION', 'REPORT')
                    for row in sections.get(section, [])), 'LIVE_NETWORK_EXTERNAL_FILE_REJECTED')
    catchments = sections.get('SUBCATCHMENTS', [])
    areas = {}
    for row in catchments:
        tokens = row['tokens']
        require(len(tokens) in (8, 9) and (len(tokens) == 8 or tokens[8] == '*'),
                'LIVE_NETWORK_CATCHMENT_INVALID')
        try:
            area = float(tokens[3])*10000
        except ValueError:
            require(False, 'LIVE_NETWORK_CATCHMENT_INVALID')
        require(math.isfinite(area) and area > 0, 'LIVE_NETWORK_CATCHMENT_INVALID')
        areas[tokens[0]] = area
    require(len({k.upper() for k in areas}) == len(catchments), 'LIVE_NETWORK_DUPLICATE_CATCHMENT')
    assignments = spec.get('stationByCatchment')
    require(isinstance(assignments, dict) and assignments and set(assignments) == set(areas)
            and all(isinstance(s, str) and re.fullmatch(r'\d{1,5}', s) for s in assignments.values()),
            'LIVE_NETWORK_ASSIGNMENT_INCOMPLETE')
    external = _external_series(sections, network, start, end)
    return text, sections, areas, external


def compile_network(network, spec):
    text, sections, areas, external = validate_network(network, spec)
    start, end = utc(spec['startUtc']), utc(spec['endUtc'])
    assignments = spec['stationByCatchment']
    data = {}
    for reference in spec['stations']:
        station, _ = read_live_station(reference, start, end)
        require(station['stationId'] not in data, 'LIVE_NETWORK_DUPLICATE_STATION')
        data[station['stationId']] = station
    require(set(assignments.values()) <= set(data), 'LIVE_NETWORK_ASSIGNMENT_INCOMPLETE')
    series, gages, totals = [], [], []
    for sid in sorted(set(assignments.values())):
        name, gauge = PREFIX+'R'+sid, PREFIX+'G'+sid
        gages.append(f'{gauge} INTENSITY 0:01 1.0 TIMESERIES {name}')
        # EPA 강우계의 +1초 탐색을 상쇄해 다음 분 강우의 조기 투입을 막는다.
        for index, depth in enumerate(data[sid]['depthsMm']):
            at = start+timedelta(minutes=index, seconds=1)
            series.append(f'{name} {at:%m/%d/%Y} {at:%H:%M:%S} {Decimal(str(depth))*60}')
        at = end+timedelta(seconds=1)
        series.append(f'{name} {at:%m/%d/%Y} {at:%H:%M:%S} 0')
        area = math.fsum(v for k,v in areas.items() if assignments[k] == sid)
        totals.append({'stationId':sid, 'catchmentAreaM2':area, 'depthMm':data[sid]['totalDepthMm'],
            'expectedVolumeM3':data[sid]['totalDepthMm']*area/1000,
            'responseSha256':data[sid]['sourceHashes'], 'sourceSha256':data[sid]['sourceHash']})
    lines = text.splitlines()
    for row in sections['SUBCATCHMENTS']:
        index = row['line']-1
        match = re.match(r'(\s*\S+\s+)(\S+)', lines[index])
        require(match is not None, 'LIVE_NETWORK_CATCHMENT_INVALID')
        lines[index] = (lines[index][:match.start(2)] + PREFIX+'G'+assignments[row['tokens'][0]]
                        + lines[index][match.end(2):])
    # 기존 강우계·시계열도 원형 보존하며 새 집수 배정만 별도 이름을 참조한다.
    _append(lines, 'RAINGAGES', gages)
    _append(lines, 'TIMESERIES', series)
    derived = '\n'.join(lines)+'\n'
    require(len(derived.encode()) <= 2_000_000, 'LIVE_NETWORK_INPUT_TOO_LARGE')
    summary = {'schemaVersion':1, 'method':METHOD, 'startUtc':start.isoformat(), 'endUtc':end.isoformat(),
        'stationByCatchment':deepcopy(assignments), 'catchmentAreasM2':areas, 'stations':totals,
        'expectedNetworkRainfallM3':math.fsum(v['expectedVolumeM3'] for v in totals),
        'originalSha256':sha(network['inputText'].encode()), 'derivedSha256':sha(derived.encode()),
        'externalTimeSeries':external, 'adapterSha256':sha(Path(__file__).read_bytes()),
        'rankingEligible':False, 'limitations':['명시한 관측소 배정과 분 내부 일정 강도 가정',
            '원 증발·초기 상태 유지; 현재 기상 선행 초기화 완료가 아님',
            '총 집수 강우 투입량 확인이며 토양·관망·지표 통합 수지 검증과 구분']}
    return network | {'inputText':derived}, summary
