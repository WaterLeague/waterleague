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
