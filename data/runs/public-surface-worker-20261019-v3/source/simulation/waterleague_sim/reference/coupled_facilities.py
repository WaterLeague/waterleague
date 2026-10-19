"""문헌 시설과 합성 집수·관망·지표의 연결 검사. 서울 자산·관측이 아님."""
from copy import deepcopy

from waterleague_sim.reference.flood_cases import coupled_case, mesh


def coupled_facility_case(design):
    import numpy as np
    model = coupled_case()
    model['surface'] = mesh(4, 2, 20, 10, bed=lambda x, y: np.ones_like(x))
    model['surface']['maxStepSeconds'] = .1
    surface = model['surface']
    owned = [i for i, tri in enumerate(surface['triangles'])
             if sum(surface['verticesM'][v][0] for v in tri) / 3 < 10]
    surface['rainfallOwner'] = ['NETWORK' if i in owned else 'SURFACE'
                               for i in range(len(surface['triangles']))]
    model['networkRainfallTriangles'] = {'S1': owned}
    model['ports'][0]['surfaceTriangles'] = [i for i in range(len(surface['triangles'])) if i not in owned]
    inp = model['network']['inputText'].replace('[STORAGE]', '''INFILTRATION GREEN_AMPT
WET_STEP 00:00:01
DRY_STEP 00:00:01
[RAINGAGES]
G INTENSITY 0:01 1.0 TIMESERIES RAIN
[TIMESERIES]
RAIN 01/01/2020 00:00 1200
RAIN 01/01/2020 00:01 0
RAIN 01/01/2020 00:02 0
[SUBCATCHMENTS]
S1 G TANK 0.01 100 10 1 0
[SUBAREAS]
S1 0.013 0.15 0 0 100 OUTLET
[INFILTRATION]
S1 50 4 0.3
[STORAGE]''')
    model['network']['inputText'] = inp
    model['evaluationMetrics'] = {
        'schemaVersion': 1, 'policyVersion': 'NUMERICAL_TEST_ONLY_v1',
        'evidence': 'NUMERICAL_TEST_EXPOSURE_NOT_SEOUL',
        'startMilliseconds': 0, 'endMilliseconds': model['durationSeconds'] * 1000,
        'networkOutfalls': ['OUT'], 'exposureTriangles': list(range(len(surface['triangles']))),
        'wetDepthThresholdM': .001}
    if design is not None:
        design = deepcopy(design)
        for row in design['placements']:
            row.update(areaM2=1, replacedImperviousM2=1, treatedImperviousM2=20)
            if row['facilityType'] == 'RAINWATER_CISTERN':
                row.update(areaM2=.1, replacedImperviousM2=.1)
                row['parameters']['storageDepthMm'] = 200
                row['parameters']['drain']['offsetMm'] = 10
            if row['facilityType'] == 'VEGETATIVE_SWALE':
                row.update(areaM2=10, replacedImperviousM2=10)
        model['connectedFacilityDesign'] = design
    return model
