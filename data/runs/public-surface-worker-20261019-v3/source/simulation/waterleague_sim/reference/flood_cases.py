"""해석·수치 검사 전용 입력. 운영 관측·서울 자산으로 사용 금지."""

def tank_input(*, initial=1, full=3, route_step=.1):
    return f'''[TITLE]
NUMERICAL_TEST_ONLY: storage and reversible boundary
[OPTIONS]
FLOW_UNITS CMS
FLOW_ROUTING DYNWAVE
START_DATE 01/01/2020
START_TIME 00:00:00
REPORT_START_DATE 01/01/2020
REPORT_START_TIME 00:00:00
END_DATE 01/01/2020
END_TIME 00:02:01
ROUTING_STEP {route_step}
MINIMUM_STEP 0.01
VARIABLE_STEP 0.75
REPORT_STEP 00:00:01
ALLOW_PONDING NO
[STORAGE]
TANK 0 {full} {initial} FUNCTIONAL 0 0 10 0 0
[OUTFALLS]
OUT 0 FIXED 0 NO
[CONDUITS]
PIPE TANK OUT 10 0.013 0 0 0 0
[XSECTIONS]
PIPE CIRCULAR 0.15 0 0 0 1
[REPORT]
NODES ALL
LINKS ALL
'''


def mesh(nx=20, ny=5, length=20., width=5., *, bed=None, water=None):
    import numpy as np
    points = np.array([(length*i/nx, width*j/ny) for j in range(ny+1) for i in range(nx+1)])
    triangles, boundary = [], {}
    for j in range(ny):
        for i in range(nx):
            a = j*(nx+1)+i
            k = len(triangles)
            triangles.extend(((a, a+1, a+nx+1), (a+1, a+nx+2, a+nx+1)))
            if i == 0: boundary[k, 1] = 'left'
            if i == nx-1: boundary[k+1, 2] = 'right'
            if j == 0: boundary[k, 2] = 'bottom'
            if j == ny-1: boundary[k+1, 0] = 'top'
    triangles = np.asarray(triangles)
    z = np.zeros(len(points)) if bed is None else bed(points[:, 0], points[:, 1])
    center_x = points[triangles, 0].mean(axis=1)
    depths = np.zeros(len(triangles)) if water is None else water(center_x, z[triangles].mean(axis=1))
    return {'schemaVersion': 1, 'coordinateSystem': 'LOCAL_REFERENCE_METRES',
            'maxStepSeconds': 1.0,
            'verticalDatum': 'ANALYTICAL_ZERO', 'evidence': 'ANALYTICAL_TEST_ONLY',
            'verticesM': points.tolist(), 'triangles': triangles.tolist(), 'elevationM': z.tolist(),
            'initialDepthM': depths.tolist(), 'manningN': [0.] * len(triangles),
            'rainfallOwner': ['SURFACE'] * len(triangles),
            'boundaryEdges': [[int(i), int(j), tag] for (i, j), tag in boundary.items()],
            'boundaryConditions': {tag: {'type': 'REFLECTIVE'} for tag in boundary.values()}}


def coupled_case(*, exchange_ms=100, initial_network=2., initial_surface=0., nx=4, conduit=False):
    import numpy as np
    surface = mesh(nx, nx, 2, 2, bed=lambda x, y: np.ones_like(x),
                   water=lambda x, z: np.full(len(x), initial_surface))
    surface['maxStepSeconds'] = .1
    inp = tank_input(initial=initial_network, full=5, route_step=.01)
    # 작은 시험 저장조의 단계별 수위 변화보다 엄격한 수렴 허용치를 명시한다.
    inp = inp.replace('MINIMUM_STEP 0.01',
        'MINIMUM_STEP 0.01\nMIN_SURFAREA 0.01\nHEAD_TOLERANCE 0.000001\nMAX_TRIALS 40')
    inp = inp.replace('FUNCTIONAL 0 0 10', 'FUNCTIONAL 0 0 1')
    inp = inp.replace('OUT 0 FIXED 0 NO', 'OUT 0 FIXED 0 NO\nSURFACE 1 FIXED 1 NO')
    inp = inp.replace('[XSECTIONS]', '[ORIFICES]\nINLET TANK SURFACE BOTTOM 1 0.65 NO 0\n[XSECTIONS]')
    inp = inp.replace('PIPE CIRCULAR 0.15 0 0 0 1', 'PIPE CIRCULAR 0.15 0 0 0 1\nINLET CIRCULAR 0.2 0 0 0')
    if not conduit:
        inp = inp.replace('[CONDUITS]\nPIPE TANK OUT 10 0.013 0 0 0 0\n', '')
        inp = inp.replace('[ORIFICES]', '[ORIFICES]\nDRAIN TANK OUT BOTTOM 0 0.65 NO 0')
        inp = inp.replace('PIPE CIRCULAR 0.15 0 0 0 1', 'DRAIN CIRCULAR 0.1 0 0 0')
    return {'schemaVersion': 1, 'evidence': 'NUMERICAL_TEST_ONLY_NOT_SEOUL', 'durationSeconds': 120,
            'maximumExchangeMilliseconds': exchange_ms, 'frameIntervalMilliseconds': 1000,
            'network': {'inputText': inp, 'coordinateSystem': surface['coordinateSystem'],
                        'verticalDatum': surface['verticalDatum']},
            'surface': surface, 'networkRainfallTriangles': {},
            'ports': [{'id': 'inlet', 'outfall': 'SURFACE', 'orifice': 'INLET', 'crestM': 1.,
                       'surfaceTriangles': list(range(len(surface['triangles']))),
                       'evidence': 'NUMERICAL_TEST_ONLY_NOT_A_REAL_ASSET'}]}


def coupled_slope_case():
    model = coupled_case(exchange_ms=100)
    model['durationSeconds'] = 30
    model['surface'] = mesh(20, 4, 10, 2, bed=lambda x, y: 1 - .05*x)
    model['surface']['maxStepSeconds'] = .1
    points = model['surface']['verticesM']
    triangles = model['surface']['triangles']
    model['ports'][0]['surfaceTriangles'] = [i for i, tri in enumerate(triangles)
        if sum(points[j][0] for j in tri) / 3 < .5]
    return model


def coupled_limited_case():
    import numpy as np
    model = coupled_case(exchange_ms=200, initial_network=0)
    model['durationSeconds'] = 5
    model['surface'] = mesh(2, 2, .2, .2, bed=lambda x, y: np.ones_like(x),
                            water=lambda x, z: np.full(len(x), .05))
    model['surface']['maxStepSeconds'] = .1
    model['ports'][0]['surfaceTriangles'] = list(range(len(model['surface']['triangles'])))
    return model


def conduit_drainage_case(segments=1, *, route_ms=1, drop_m=0., flow_m3s=.05, surcharge_method=None):
    """동일한 건조 초기 상태·총 관로 길이·유입량의 수치 분할 비교 입력."""
    if (type(segments) is not int or not 1 <= segments <= 100 or route_ms not in (1, 2, 5, 10)
            or surcharge_method not in (None, 'EXTRAN', 'SLOT')):
        raise ValueError('수치 사례 분할 범위 오류')
    model = coupled_case(initial_network=0., conduit=True)
    text = model['network']['inputText']
    if surcharge_method is not None:
        text = text.replace('FLOW_ROUTING DYNWAVE', f'FLOW_ROUTING DYNWAVE\nSURCHARGE_METHOD {surcharge_method}')
    text = text.replace('ROUTING_STEP 0.01', f'ROUTING_STEP {route_ms / 1000}')
    text = text.replace('MINIMUM_STEP 0.01', f'MINIMUM_STEP {route_ms / 1000}')
    text = text.replace('MAX_TRIALS 40', 'MAX_TRIALS 200')
    text = text.replace('OUT 0 FIXED 0 NO', f'OUT {-drop_m} FIXED {-drop_m} NO')
    nodes = ['TANK', *[f'J{i}' for i in range(1, segments)], 'OUT']
    links = '\n'.join(f'P{i} {nodes[i]} {nodes[i+1]} {10 / segments} .013 0 0 0 0'
                      for i in range(segments))
    sections = '\n'.join(f'P{i} CIRCULAR .15 0 0 0 1' for i in range(segments))
    text = text.replace('PIPE TANK OUT 10 0.013 0 0 0 0', links)
    text = text.replace('PIPE CIRCULAR 0.15 0 0 0 1', sections)
    if segments > 1:
        text += '\n[JUNCTIONS]\n' + '\n'.join(
            f'J{i} {-drop_m*i/segments} 5 0 0 0' for i in range(1, segments)) + '\n'
    text += f'''\n[INFLOWS]
TANK FLOW LOAD FLOW 1.0 1.0
[TIMESERIES]
LOAD 01/01/2020 00:00:00 {flow_m3s}
LOAD 01/01/2020 00:00:30 {flow_m3s}
LOAD 01/01/2020 00:00:31 0
LOAD 01/01/2020 00:02:01 0
'''
    model['network']['inputText'] = text
    return model


def coupled_conduit_surcharge_case(*, route_ms=1, exchange_ms=100, nx=4):
    """빈 시설의 시간별 유입으로 월류·재유입을 만드는 공식 SLOT 수치 사례."""
    model = conduit_drainage_case(flow_m3s=.1, route_ms=route_ms, surcharge_method='SLOT')
    template = coupled_case(initial_network=0., nx=nx)
    model['surface'], model['ports'] = template['surface'], template['ports']
    model['maximumExchangeMilliseconds'] = exchange_ms
    model['evaluationMetrics'] = {
        'schemaVersion': 1, 'policyVersion': 'NUMERICAL_CONDUIT_SURCHARGE_v1',
        'evidence': 'NUMERICAL_TEST_ONLY_NOT_SEOUL', 'startMilliseconds': 0,
        'endMilliseconds': 120000, 'networkOutfalls': ['OUT'],
        'exposureTriangles': list(range(len(model['surface']['triangles']))),
        'wetDepthThresholdM': .001}
    return model
