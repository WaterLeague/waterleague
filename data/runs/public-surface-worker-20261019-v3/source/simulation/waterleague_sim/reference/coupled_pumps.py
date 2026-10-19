"""공개 펌프 곡선의 하류 월류·재유입 수치 사례. 서울 현장 자료 아님."""
from .connected_pumps import case as pump_case
from .flood_cases import mesh
from ..ingestion.published_network import digest


def case(*, pump=True, exchange_ms=100, frame_ms=1000, start_seconds=10, end_seconds=600,
         pressure_limit=20, route_step=.01):
    import numpy as np
    raw, design = pump_case(seconds=600, step=route_step, pressure_limit=pressure_limit)
    text = raw.decode().replace('FUNCTIONAL 0 0 100 0 0', 'FUNCTIONAL 0 0 10 0 0')
    text = text.replace('FUNCTIONAL 0 0 1000 0 0', 'FUNCTIONAL 0 0 20 0 0')
    text = text.replace('END_TIME 00:10:00', 'END_TIME 00:10:01')
    text = text.replace('O 4 FIXED 5 NO', 'O 4 FIXED 4.5 NO\nSURFACE 5 FIXED 5 NO')
    text = text.replace('TAIL CIRCULAR 2', 'TAIL CIRCULAR .15')
    text = text.replace('[ORIFICES]', '[ORIFICES]\nINLET R SURFACE BOTTOM 1 .65 NO 0')
    text = text.replace('[XSECTIONS]', '[XSECTIONS]\nINLET CIRCULAR .2 0 0 0')
    surface = mesh(4, 4, 5, 4, bed=lambda x, y: np.full(len(x), 5.))
    surface.update(schemaVersion=2, maxStepSeconds=.1, manningN=[.03]*len(surface['triangles']))
    cells = [i for i, tri in enumerate(surface['triangles'])
             if sum(surface['verticesM'][j][0] for j in tri)/3 < 1.25]
    model = {'schemaVersion': 1, 'evidence': 'NUMERICAL_PUBLIC_PUMP_CURVE_NOT_SEOUL',
        'durationSeconds': 600, 'maximumExchangeMilliseconds': exchange_ms,
        'frameIntervalMilliseconds': frame_ms, 'networkRainfallTriangles': {},
        'surface': surface, 'network': {'inputText': text, 'coordinateSystem': surface['coordinateSystem'],
            'verticalDatum': surface['verticalDatum']},
        'ports': [{'id': 'inlet', 'outfall': 'SURFACE', 'orifice': 'INLET', 'crestM': 5.,
            'surfaceTriangles': cells, 'evidence': '명시적 수치 시험 개구부·지표, 서울 시설 아님'}],
        'evaluationMetrics': {'schemaVersion': 1, 'policyVersion': 'COUPLED_PUMP_DIAGNOSTIC_v1',
            'evidence': 'NUMERICAL_TEST_ONLY', 'startMilliseconds': round(start_seconds*1000),
            'endMilliseconds': round(end_seconds*1000), 'networkOutfalls': ['O'],
            'exposureTriangles': list(range(len(surface['triangles']))), 'wetDepthThresholdM': .001}}
    if pump:
        design['sourceNetworkSha256'] = digest(text.encode())
        model['connectedPumpDesign'] = design
    return model


def initialized(lids, *, route_step=.25):
    from .storage_composition import initialized as composition
    from .connected_storage import design as storage_design
    from ..evaluation.values import digest as model_digest
    model = composition(lids, route_step=route_step)
    pond = model.pop('surfaceBasinDesign')
    raw = model['network']['inputText'].encode()
    model['connectedStorageDesign'] = storage_design(raw, invert=-4, depth=6, area=400)
    _, design = pump_case()
    design['sourceNetworkSha256'] = digest(raw)
    design['placements'][0].update(fromNode='WLST_Tank', toNode='RECEIVER')
    model['connectedPumpDesign'] = design
    pond['sourceModelSha256'] = model_digest(model)
    model['surfaceBasinDesign'] = pond
    return model


def initialized_profile(lids, *, route_step=.05, exchange_ms=60000, numerical_node_area_m2=None,
                        max_trials=None):
    from ..evaluation.values import digest as model_digest
    model = initialized(lids)
    pond = model.pop('surfaceBasinDesign')
    if numerical_node_area_m2 is not None:
        text = model['network']['inputText'].replace('MIN_SURFAREA 0.01',
            f'MIN_SURFAREA {numerical_node_area_m2:.15g}')
        model['network']['inputText'] = text
        for key in ('connectedStorageDesign', 'connectedPumpDesign'):
            model[key]['sourceNetworkSha256'] = digest(text.encode())
        model['numericalFixtureVariation'] = {'classification': 'NUMERICAL_AREA_NOT_SITE_GEOMETRY',
            'originalDeclaredNodeAreaM2': .01, 'declaredNodeAreaM2': numerical_node_area_m2,
            'zeroPolicy': 'EPA_5_2_4_DEFAULT_12_566_SQUARE_FEET'}
    model['networkNumericalProfile'] = {'id': 'coupled-pump-slot-v1', 'options': {
        'SURCHARGE_METHOD': 'SLOT', 'ROUTING_STEP': route_step}}
    if max_trials is not None:
        model['networkNumericalProfile']['id'] = 'coupled-pump-slot-trials-v2'
        model['networkNumericalProfile']['options']['MAX_TRIALS'] = max_trials
    model['maximumExchangeMilliseconds'] = exchange_ms
    pond['sourceModelSha256'] = model_digest(model)
    model['surfaceBasinDesign'] = pond
    return model
