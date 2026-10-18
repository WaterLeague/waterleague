"""SWMM 수평 유입부와 ANUGA의 보존적 명시적 분할 결합."""
import hashlib
from bisect import bisect_right
import json
import math
from pathlib import Path

from waterleague_sim.engine.flood_errors import FloodModelError, require
from waterleague_sim.engine.flood_process import EngineProcess
from waterleague_sim.engine.flood_metrics import specification_hash, validate_metrics
from waterleague_sim.forcing.observed_rainfall import compile_rainfall, require_network_clock
from waterleague_sim.forcing.stage import require_stage_clock
from waterleague_sim.forcing.network_stage import prepare_network_stage
from waterleague_sim.engine.surface_infiltration import validate as validate_infiltration
from waterleague_sim.forcing.surface_evaporation import require_evaporation_clock
from waterleague_sim.engine.surface_exchange import DRY_EXCHANGE_POLICY, DRY_TRANSFER_TOLERANCE_M3


def _write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + '\n')


def _validate(model):
    require(model.get('schemaVersion') == 1 and model.get('evidence'), 'COUPLED_REFERENCE_REQUIRED')
    surface, network = model['surface'], model['network']
    require(model.get('dryExchangePolicy') in (None, DRY_EXCHANGE_POLICY), 'EXCHANGE_DRY_POLICY_INVALID')
    if surface.get('infiltration') is not None:
        validate_infiltration(surface['infiltration'], surface['rainfallOwner'])
    if 'terrainProvenance' in surface:
        require(surface['terrainProvenance'].get('absoluteVerticalReferenceVerified') is True,
                'COUPLED_VERTICAL_REFERENCE_UNVERIFIED')
    for key in ('coordinateSystem', 'verticalDatum'):
        require(surface.get(key) and network.get(key) == surface[key], 'COUPLED_REFERENCE_MISMATCH')
    for key in ('durationSeconds', 'maximumExchangeMilliseconds', 'frameIntervalMilliseconds'):
        require(type(model.get(key)) is int and model[key] > 0, 'COUPLED_TIMING_INVALID')
    require(model['maximumExchangeMilliseconds'] <= 60_000, 'COUPLED_TIMING_INVALID')
    if model.get('evaluationMetrics') is not None:
        validate_metrics(model['evaluationMetrics'], len(surface['triangles']), model['durationSeconds'])
        require(not any('evaluationMetrics' in part for part in (surface, network)),
                'COUPLED_METRICS_SPECIFICATION_CONFLICT')
    # 관망 강우 면적은 지정된 지표 격자와 일치해야 하며 직접 강우에서는 제외한다.
    subcatchments, section = {}, ''
    units = None
    for line in network['inputText'].splitlines():
        tokens = line.split(';', 1)[0].split()
        if tokens and tokens[0].startswith('['):
            section = tokens[0].upper()
        elif tokens and section == '[OPTIONS]' and tokens[0].upper() == 'FLOW_UNITS':
            units = tokens[1].upper()
        elif tokens and section == '[SUBCATCHMENTS]':
            subcatchments[tokens[0]] = float(tokens[3])
    ownership = model.get('networkRainfallTriangles', {})
    require(isinstance(ownership, dict) and set(ownership) == set(subcatchments),
            'COUPLED_RAINFALL_OWNERSHIP_INCOMPLETE')
    used = set()
    for name, cells in ownership.items():
        require(isinstance(cells, list) and cells and all(type(i) is int and 0 <= i < len(surface['triangles'])
                for i in cells) and len(set(cells)) == len(cells) and not used.intersection(cells)
                and all(surface['rainfallOwner'][i] == 'NETWORK' for i in cells),
                'COUPLED_RAINFALL_OVERLAP')
        used.update(cells)
        area = 0.
        for i in cells:
            a, b, c = [surface['verticesM'][j] for j in surface['triangles'][i]]
            area += abs((b[0]-a[0])*(c[1]-a[1]) - (b[1]-a[1])*(c[0]-a[0])) / 2
        expected = subcatchments[name] * (10_000 if units == 'CMS' else 4046.8564224)
        require(math.isclose(area, expected, abs_tol=1e-6, rel_tol=1e-6), 'COUPLED_RAINFALL_AREA_MISMATCH')
    require(used == {i for i, owner in enumerate(surface['rainfallOwner']) if owner == 'NETWORK'},
            'COUPLED_RAINFALL_OWNERSHIP_INCOMPLETE')
    for collection in ('networkForcing', 'surfaceRainfall'):
        events = model.get(collection, [])
        require(isinstance(events, list) and len(events) <= 100_000, 'COUPLED_FORCING_INVALID')
        previous = -1
        seen = set()
        for row in events:
            time = row.get('timeMilliseconds')
            key = (time, row.get('node'))
            require(type(time) is int and 0 <= time < model['durationSeconds'] * 1000
                    and time >= previous and key not in seen and row.get('evidence'), 'COUPLED_FORCING_INVALID')
            previous = time
            seen.add(key)


def _balance(network, surface, ports):
    n = network['totals']
    outward = sum(p['networkToSurfaceM3'] for p in ports.values())
    inward = sum(p['surfaceToNetworkM3'] for p in ports.values())
    incoming = sum(n[k] for k in ('dryWeatherInflowM3', 'runoffInflowM3', 'groundwaterInflowM3',
                                  'rdiiInflowM3', 'externalInflowM3')) - inward
    outgoing = sum(n[k] for k in ('outflowM3', 'floodingM3', 'evaporationM3', 'seepageM3',
                                  'reactionLossM3')) - outward
    result = {'networkExternalInflowM3': incoming, 'networkExternalOutflowAndLossM3': outgoing,
            'surfaceExternalNetInflowM3': surface['externalSourceNetInflowM3'] + surface['boundaryNetInflowM3'],
            'networkStorageM3': n['storageM3'], 'surfaceStorageM3': surface['storageM3'],
            'networkToSurfaceM3': outward, 'surfaceToNetworkM3': inward,
            'exchangeCancellationResidualM3': outward - inward - surface['exchangeNetInflowM3']}
    if 'infiltrationM3' in surface:
        result.update(surfaceRainfallM3=surface['rainfallM3'], surfaceInfiltrationM3=surface['infiltrationM3'],
                      surfaceBoundaryNetInflowM3=surface['boundaryNetInflowM3'])
    if 'surfaceEvaporationM3' in surface:
        result.update({key: surface[key] for key in
                       ('surfaceEvaporationM3', 'potentialSurfaceEvaporationM3',
                        'unmetSurfaceEvaporationM3', 'surfaceEvaporationRoundoffM3')})
    return result


def run_coupled(model, directory):
    _validate(model)
    facility_design = None
    storage_design, storage_raw, storage_summary = None, None, None
    original_model = model
    basin_design, basin_model = None, None
    composition, composed_raw = None, None
    if 'surfaceBasinDesign' in model:
        from waterleague_sim.engine.surface_basin import compile_basin
        model, basin_design = compile_basin(model)
        basin_model = model
        _validate(model)
    initialization, evaluation_origin, evaluation_final, evaluation_balance = None, None, None, None
    if 'connectedStorageDesign' in model:
        require(model.get('evaluationMetrics') is not None, 'COUPLED_STORAGE_METRICS_REQUIRED')
        from waterleague_sim.engine.connected_storage import compile_storage
        storage_raw, storage_design = compile_storage(original_model['network']['inputText'].encode(),
                                                      model['connectedStorageDesign'])
        composed_raw = storage_raw
        if basin_design is not None:
            from waterleague_sim.engine.storage_composition import compose_storage
            composed_raw, composition = compose_storage(original_model, model, storage_raw, storage_design)
        model = model | {'network': model['network'] | {'inputText': composed_raw.decode()}}
    if 'initialization' in model:
        from waterleague_sim.forcing.coupled_initialization import prepare_initialized_coupling
        initialization = prepare_initialized_coupling(model)
        model = initialization.model
        _validate(model)
    if 'connectedFacilityDesign' in model:
        require(model.get('evaluationMetrics') is not None, 'COUPLED_FACILITY_METRICS_REQUIRED')
        from waterleague_sim.engine.connected_facilities import compile_design
        raw, facility_design = compile_design(model['network']['inputText'].encode(), model['connectedFacilityDesign'])
        model = model | {'network': model['network'] | {'inputText': raw.decode()}}
    evaporation = require_evaporation_clock(model['surface'], duration=model['durationSeconds'],
                         rainfall=model.get('observedRainfall'), network=model['network'])
    stages = require_stage_clock(model['surface'], duration=model['durationSeconds'],
                                 rainfall=model.get('observedRainfall'), network=model['network'])
    network_stages = prepare_network_stage(model['network'] | {'ports': model['ports']},
                                           evaluation_seconds=model['durationSeconds'])
    observed = None
    if model.get('observedRainfall') is not None:
        require(not model.get('surfaceRainfall') and model['surface'].get('rainfallStationIds') is None,
                'COUPLED_RAINFALL_FORCING_CONFLICT')
        require_network_clock(model['network'], model['observedRainfall'])
        observed = (initialization.schedule if initialization is not None else
                    compile_rainfall(model['observedRainfall'], model['surface'], model['durationSeconds']))
    directory = Path(directory).resolve()
    require(not directory.exists(), 'COUPLED_OUTPUT_EXISTS')
    directory.mkdir(parents=True)
    _write(directory / 'coupled-input.json', original_model)
    if basin_design is not None:
        _write(directory / 'surface-basin-design.json', basin_design)
        _write(directory / 'basin-coupled-input.json', basin_model)
    if storage_design is not None:
        _write(directory / 'connected-storage-design.json', storage_design)
        (directory / 'storage-network.inp').write_bytes(storage_raw)
    if composition is not None:
        _write(directory / 'connected-design-composition.json', composition)
        (directory / 'composed-network.inp').write_bytes(composed_raw)
    if initialization is not None:
        _write(directory / 'initialized-coupled-input.json', initialization.model)
        _write(directory / 'initialization-forcing.json', initialization.summary)
        initialization.network.archive(directory / 'network-initialization')
    if facility_design is not None:
        _write(directory / 'connected-facility-design.json', facility_design)
        (directory / 'facility-network.inp').write_bytes(raw)
    if observed is not None:
        observed.archive(directory / 'observed-rainfall')
    ports = model['ports']
    network_model = model['network'] | {'ports': ports}
    surface_model = {'surface': model['surface'], 'ports': ports}
    if model.get('dryExchangePolicy') is not None:
        surface_model['dryExchangePolicy'] = model['dryExchangePolicy']
    metric_spec = model.get('evaluationMetrics')
    if metric_spec is not None:
        network_model = network_model | {'evaluationMetrics': metric_spec}
        surface_model = surface_model | {'surface': model['surface'] | {'evaluationMetrics': metric_spec}}
    if observed is not None:
        surface_model['surface'] = surface_model['surface'] | {
            'rainfallStationIds': model['observedRainfall']['stationByTriangle']}
    duration = model['durationSeconds'] * 1000
    events = {}
    for collection in ('networkForcing', 'surfaceRainfall'):
        for row in model.get(collection, []):
            events.setdefault(row['timeMilliseconds'], []).append((collection, row))
    if observed is not None:
        for row in observed.events:
            events.setdefault(row['timeMilliseconds'], []).append(('observedRainfall', row))
    stage_times = {round(t * 1000) for series in (*stages.values(), *network_stages.series.values())
                   for t in series.knots}
    if evaporation is not None:
        stage_times.update(round(t * 1000) for t in evaporation.knots)
    if initialization is not None:
        stage_times.add(initialization.summary['warmupSeconds'] * 1000)
    event_times = sorted(set(events) | stage_times | {duration})
    clock, nstate, state = 0, None, None
    network_engine = ('coupled_facility_network' if facility_design is not None else
                      'network_metrics' if metric_spec is not None else 'network_exchange')
    try:
        with EngineProcess(network_engine,
                           network_model, directory / 'network',
                           evaluation_seconds=model['durationSeconds']) as network:
            with EngineProcess('surface_exchange', surface_model, directory / 'surface') as surface:
                state = surface.call('port_state')
                nstate = network.info['initial']
                if facility_design is not None:
                    expected = {(row['subcatchmentId'], row['swmmId']) for row in facility_design['facilities']}
                    actual = [(row['subcatchmentId'], row['swmmId']) for row in nstate['facilities']]
                    require(len(actual) == len(expected) and set(actual) == expected,
                            'COUPLED_FACILITY_OBSERVER_MISMATCH')
                    _write(directory / 'connected-facility-initial.json', nstate['facilities'])
                initial_storage = nstate['totals']['initialStorageM3'] + state['storageM3']
                heads = {key: row['headM'] for key, row in state['ports'].items()}
                previous_ports = network.call('port_state', heads)
                clock, steps, smallest = 0, 0, model['maximumExchangeMilliseconds']
                next_frame = model['frameIntervalMilliseconds']
                with (directory / 'exchange-ledger.jsonl').open('x') as ledger:
                    while clock < duration:
                        for collection, row in events.get(clock, []):
                            if collection == 'networkForcing':
                                network.call('set_inflow', row['node'], row['flowM3s'])
                            elif collection == 'observedRainfall':
                                surface.call('set_station_rainfall', row['ratesMmHByStation'])
                            else:
                                surface.call('set_rainfall', row['ratesMmH'])
                        heads = {key: row['headM'] for key, row in state['ports'].items()}
                        hydraulic = network.call('port_state', heads)
                        require(all(row['openingAreaM2'] <= state['ports'][key]['regionAreaM2']
                                    for key, row in hydraulic.items()), 'COUPLED_OPENING_EXCEEDS_REGION')
                        step = min(model['maximumExchangeMilliseconds'], duration - clock,
                                   event_times[bisect_right(event_times, clock)] - clock)
                        for key, row in hydraulic.items():
                            bound = max(row['maximumInflowM3s'], row['previousInflowM3s'])
                            if bound > 0:
                                # 수치적 분할 간격 제한이며 실제 유입부 개방률을 조작하지 않는다.
                                limit = math.floor(1000 * .25 * state['ports'][key]['availableM3'] / bound)
                                # 건조 경계의 직전 유량 적분 꼬리만 최소 간격에서 제한된 잔차로 보존한다.
                                if (limit == 0 and model.get('dryExchangePolicy') == DRY_EXCHANGE_POLICY
                                        and row['maximumInflowM3s'] == 0
                                        and row['previousInflowM3s']*.001/2 <= DRY_TRANSFER_TOLERANCE_M3):
                                    limit = 1
                                step = min(step, limit)
                        require(step >= 1, 'COUPLED_SUBMILLISECOND_STEP_REQUIRED')
                        result = network.call('exchange_step', step, heads)
                        nstate, new_ports = result['network'], result['ports']
                        transfers, entries = {}, []
                        for key, row in new_ports.items():
                            outward = row['networkToSurfaceM3'] - previous_ports[key]['networkToSurfaceM3']
                            inward = row['surfaceToNetworkM3'] - previous_ports[key]['surfaceToNetworkM3']
                            available = state['ports'][key]['availableM3']
                            require(outward >= 0 and inward >= 0, 'COUPLED_CUMULATIVE_VOLUME_REVERSED')
                            transfers[key] = outward - inward
                            entries.append({'port': key, 'surfaceHeadM': heads[key],
                                'networkHeadBeforeM': hydraulic[key]['networkHeadM'],
                                'networkHeadAfterM': row['networkHeadM'], 'availableBeforeM3': available,
                                'networkToSurfaceM3': outward, 'surfaceToNetworkM3': inward})
                        # 적용 전 원장을 남겨 실패한 단계의 관망 인출량도 복구 가능하게 한다.
                        ledger.write(json.dumps({'phase': 'NETWORK_ADVANCED', 'startMilliseconds': clock,
                            'endMilliseconds': clock + step, 'transfers': entries}, allow_nan=False) + '\n')
                        ledger.flush()
                        tolerance = DRY_TRANSFER_TOLERANCE_M3 if model.get('dryExchangePolicy') else 0.
                        require(all(e['surfaceToNetworkM3'] <= e['availableBeforeM3']+tolerance for e in entries),
                                'COUPLED_SURFACE_OVERDRAW')
                        require(nstate['totals']['floodingM3'] <= 1e-9, 'COUPLED_UNMAPPED_NODE_FLOODING')
                        applied = surface.call('apply_exchange', transfers)
                        state = surface.call('advance_exchange', step)
                        clock += step
                        require(math.isclose(state['timeSeconds'], clock / 1000, abs_tol=1e-8, rel_tol=0),
                                'COUPLED_CLOCK_MISMATCH')
                        balance = _balance(nstate, state, new_ports)
                        residual = (initial_storage + balance['networkExternalInflowM3']
                            + balance['surfaceExternalNetInflowM3'] - balance['networkExternalOutflowAndLossM3']
                            - balance['networkStorageM3'] - balance['surfaceStorageM3'])
                        balance['balanceResidualM3'] = residual
                        require(abs(balance['exchangeCancellationResidualM3']) < 1e-8,
                                'COUPLED_EXCHANGE_LEDGER_MISMATCH')
                        ledger.write(json.dumps({'phase': 'BOTH_APPLIED', 'endMilliseconds': clock,
                            'surfaceTransfers': applied['transfers'], 'balance': balance}, allow_nan=False) + '\n')
                        previous_ports = new_ports
                        if initialization is not None and clock == initialization.summary['warmupSeconds']*1000:
                            evaluation_origin = {'network': network.call('snapshot'),
                                'surface': surface.call('initialization_state'),
                                'surfaceExchange': state, 'ports': new_ports}
                            _write(directory / 'evaluation-initial-state.json', evaluation_origin)
                        smallest = min(smallest, step)
                        steps += 1
                        require(steps <= 2_000_000, 'COUPLED_STEP_LIMIT_EXCEEDED')
                        if clock >= next_frame:
                            surface.call('store_frame')
                            with (directory / 'network-frames.jsonl').open('a') as stream:
                                stream.write(json.dumps(network.call('snapshot'), allow_nan=False) + '\n')
                            while next_frame <= clock:
                                next_frame += model['frameIntervalMilliseconds']
                if initialization is not None:
                    require(evaluation_origin is not None, 'COUPLED_INITIALIZATION_BOUNDARY_MISSING')
                    from waterleague_sim.forcing.coupled_initialization import evaluation_ledger
                    evaluation_final = {'network': network.call('snapshot'),
                        'surface': surface.call('initialization_state'),
                        'surfaceExchange': state, 'ports': previous_ports}
                    _write(directory / 'evaluation-final-state.json', evaluation_final)
                    evaluation_balance = evaluation_ledger(evaluation_origin, evaluation_final)
                    expected = observed.summary['evaluationRainfall']['expectedSurfaceRainfallM3']
                    require(math.isclose(evaluation_balance['surface']['rainfallM3'], expected,
                            abs_tol=1e-8, rel_tol=1e-8), 'OBSERVED_EVALUATION_RAIN_VOLUME_MISMATCH')
                nresult, sresult = network.call('finish'), surface.call('finish')
                if storage_design is not None:
                    from waterleague_sim.engine.connected_storage import result_summary
                    storage_summary = result_summary(storage_design, nresult['initial'], nresult['final'],
                        evaluation_origin['network'] if evaluation_origin is not None else None)
                scale = max(initial_storage + balance['networkExternalInflowM3']
                            + max(0, balance['surfaceExternalNetInflowM3']),
                            balance['networkStorageM3'] + balance['surfaceStorageM3'])
                passed = (nresult['numericalStatus'] == sresult['numericalStatus'] == 'PASSED'
                          and abs(residual) <= max(1e-8, .01 * scale)
                          and (storage_summary is None or storage_summary['numericalStatus'] == 'PASSED')
                          and (evaluation_balance is None or evaluation_balance['numericalStatus'] == 'PASSED'))
                if observed is not None:
                    expected_rain = observed.summary['expectedSurfaceRainfallM3']
                    applied_rain = state.get('rainfallM3', state['externalSourceNetInflowM3'])
                    require(math.isclose(applied_rain, expected_rain,
                                        rel_tol=1e-8, abs_tol=1e-8), 'OBSERVED_RAIN_VOLUME_MISMATCH')
                result = {'schemaVersion': 1, 'classification': model['evidence'],
                    'method': 'EXPLICIT_NETWORK_EXCHANGE_THEN_SURFACE_FLOW',
                    'durationSeconds': model['durationSeconds'], 'steps': steps,
                    'maximumExchangeMilliseconds': model['maximumExchangeMilliseconds'],
                    'smallestExchangeMilliseconds': smallest, 'availabilityFractionLimit': .25,
                    'initialStorageM3': initial_storage, 'balance': balance,
                    'networkRoutingContinuityPercent': nresult['routingContinuityPercent'],
                    'networkConvergence': nresult['convergence'],
                    'networkNumericalConfiguration': nresult['numericalConfiguration'],
                    'networkNumericalQuality': nresult['numericalQuality'],
                    'networkNumericalStatus': nresult['numericalStatus'],
                    'surfaceNumericalStatus': sresult['numericalStatus'],
                    'surfaceNumericalConfiguration': sresult['numericalConfiguration'],
                    'numericalStatus': 'PASSED' if passed else 'FAILED',
                    'codeSha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                    'limitations': ['명시적 분할 오차의 교환 간격 세분 비교 필요',
                        '유입부 영역 평균 수두와 수평 운동량 없는 수직 유입 가정',
                        '관망 라우팅·지표 물수지 범위; 유역 토양·증발산 전체 수지 아님',
                        '연결되지 않은 노드 월류는 실패 처리, 임의 지표 위치 할당 없음'],
                    'files': {str(p.relative_to(directory)): hashlib.sha256(p.read_bytes()).hexdigest()
                              for p in sorted(directory.rglob('*')) if p.is_file()}}
                if model.get('dryExchangePolicy') is not None:
                    result['dryExchangeRoundoff'] = state['dryExchangeRoundoff']
                if storage_summary is not None:
                    result['connectedStorage'] = storage_summary
                if basin_design is not None:
                    from waterleague_sim.engine.surface_basin import result_summary as basin_summary
                    result['surfaceBasins'] = basin_summary(basin_design, sresult,
                        evaluation_origin['surface']['surface'] if evaluation_origin is not None else None)
                if observed is not None:
                    result['observedRainfall'] = observed.summary | {
                        'appliedSurfaceRainfallM3': applied_rain,
                        'volumeResidualM3': applied_rain - expected_rain}
                if initialization is not None:
                    result['initialization'] = initialization.summary | {'evaluationLedger': evaluation_balance,
                        'limitations': ['선행 시드·기간의 민감도 비교 필요; 현장 초기 상태 관측 아님',
                            '별도 시설 수지와 라우팅/지표 수지이며 유역 토양 전체 수지 아님']}
                if 'infiltration' in sresult:
                    result['surfaceInfiltration'] = sresult['infiltration']
                if 'surfaceFrames' in sresult:
                    result['surfaceFrames'] = sresult['surfaceFrames'] | {
                        'catalogFile': 'surface/' + sresult['surfaceFrames']['catalogFile']}
                if 'evaporation' in sresult:
                    result['surfaceEvaporation'] = sresult['evaporation']
                if 'numericalQuality' in sresult:
                    result['surfaceNumericalQuality'] = sresult['numericalQuality']
                if facility_design is not None:
                    result['connectedFacilities'] = {
                        'design': facility_design,
                        'quality': nresult['facilityQuality'],
                        'initial': nresult['initial']['facilities'],
                        'final': nresult['final']['facilities'],
                        'routingTimeSeconds': nresult['final']['totals']['timeSeconds'],
                        'scope': 'SEPARATE_NATIVE_HYDROLOGY_BALANCE_NOT_EVALUATION_WINDOW_METRICS',
                        'routingSurfaceBalanceIncludesFacilityStorage': False,
                        'routingSurfaceBalanceAddsFacilityOutflows': False}
                if metric_spec is not None:
                    nm, sm = nresult['evaluationMetrics'], sresult['evaluationMetrics']
                    spec_hash = specification_hash(metric_spec)
                    require(nm['specificationSha256'] == sm['specificationSha256'] == spec_hash,
                            'COUPLED_METRICS_SPECIFICATION_MISMATCH')
                    complete = nm['complete'] and sm['complete']
                    result['evaluationMetrics'] = {'specification': metric_spec,
                        'specificationSha256': spec_hash,
                        'status': 'NUMERICAL_DIAGNOSTIC' if complete and passed else 'FAILED_DIAGNOSTIC',
                        'rankingEligible': False, 'complete': complete,
                        'network': nm, 'surface': sm,
                        'raw': {'outwardVolumeM3': nm['combined']['outwardVolumeM3'],
                                'peakOutwardM3s': nm['combined']['peakOutwardM3s'],
                                'depthAreaTimeM3Hours': sm['depthAreaTimeM3Hours']}}
                _write(directory / 'coupled-result.json', result)
                return result
    except BaseException as error:
        _write(directory / 'coupled-failure.json', {'status': 'FAILED',
            'code': str(error) if isinstance(error, FloodModelError) else 'COUPLED_ENGINE_FAILED',
            'lastSynchronizedMilliseconds': clock, 'lastNetwork': nstate, 'lastSurface': state})
        raise
