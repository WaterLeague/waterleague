"""덮개 강우·관망 역압용 명시적 수치 진단. 실제 서울 시설 아님."""
from .flood_cases import tank_input
from ..ingestion.published_network import digest


def source(*, backwater=False):
    text = tank_input(initial=.5 if backwater else 0, full=3, route_step=.01)
    text = text.replace('MINIMUM_STEP 0.01', 'MINIMUM_STEP 0.001\nSURCHARGE_METHOD SLOT\n'
        'MIN_SURFAREA 0.01\nHEAD_TOLERANCE 0.000001\nMAX_TRIALS 200\n'
        'INFILTRATION GREEN_AMPT\nWET_STEP 00:00:01\nDRY_STEP 00:00:01')
    if backwater: text = text.replace('OUT 0 FIXED 0 NO', 'OUT 0 FIXED 0.5 NO')
    return (text + '''
[RAINGAGES]
G INTENSITY 0:01 1 TIMESERIES RAIN
[TIMESERIES]
RAIN 01/01/2020 00:00 3600
RAIN 01/01/2020 00:01 0
RAIN 01/01/2020 00:02 0
[SUBCATCHMENTS]
S1 G TANK 0.01 100 10 1 0
[SUBAREAS]
S1 .013 .15 0 0 100 OUTLET
[INFILTRATION]
S1 50 4 .3
''').encode()


def design(raw, *, flap=True):
    return {'schemaVersion': 1, 'sourceNetworkSha256': digest(raw), 'id': 'Cistern',
        'subcatchmentId': 'S1', 'captureAreaM2': 20., 'footprintM2': 1., 'invertM': 0.,
        'depthAreaCurve': [{'depthM': 0., 'areaM2': 1.}, {'depthM': 1.4, 'areaM2': 1.}],
        'initialDepthM': 0.,
        'drain': {'crestM': .05, 'diameterM': .02, 'dischargeCoefficient': .65, 'flapGate': flap},
        'overflow': {'crestM': 1., 'diameterM': .1, 'dischargeCoefficient': .65, 'flapGate': flap},
        'evidence': 'NUMERICAL_DIAGNOSTIC_NOT_SEOUL_MEASUREMENT'}


def hydrology_series(raw, directory):
    """원 EPA 공개 C API의 보고 시계열 대조. 물리 상태·시간 간격 변경 없음."""
    import ctypes as C
    import math
    import os
    from pathlib import Path
    import struct
    from ..engine.flood_errors import require
    from ..engine.swmm import library_path
    from ..ingestion.published_network import records
    directory=Path(directory);directory.mkdir(parents=True, exist_ok=False)
    inp,rpt,out=[directory/name for name in ('input.inp','report.rpt','result.out')]
    inp.write_bytes(raw)
    rows=[r['tokens'] for r in records(raw)[1]['SUBCATCHMENTS']]
    areas=[float(r[3])*10000 for r in rows]
    lib=C.CDLL(str(library_path()))
    require(lib.swmm_getVersion()==52004,'CISTERN_REFERENCE_VERSION_CHANGED')
    lib.swmm_getSavedValue.argtypes=[C.c_int,C.c_int,C.c_int]
    lib.swmm_getSavedValue.restype=C.c_double
    def check(code): require(code==0,'CISTERN_REFERENCE_ENGINE_FAILED')
    try:
        check(lib.swmm_open(os.fsencode(inp),os.fsencode(rpt),os.fsencode(out)))
        check(lib.swmm_start(1));elapsed=C.c_double()
        while True:
            check(lib.swmm_step(C.byref(elapsed)))
            if elapsed.value==0: break
        check(lib.swmm_end());check(lib.swmm_report())
        footer=struct.unpack('<6i',out.read_bytes()[-24:])
        require(footer[3]>0 and footer[4]==0 and footer[5]==516114522,'CISTERN_REFERENCE_OUTPUT_INVALID')
        values={}
        for label,prop in (('rainfallMmM2H',202),('evaporationMmM2Day',203),('infiltrationMmM2H',204),('runoffM3s',205)):
            values[label]=[math.fsum(lib.swmm_getSavedValue(prop,i,period)*(1 if prop==205 else area)
                for i,area in enumerate(areas)) for period in range(1,footer[3]+1)]
        require(all(math.isfinite(v) for series in values.values() for v in series),'CISTERN_REFERENCE_NONFINITE')
        return values
    finally: lib.swmm_close()
