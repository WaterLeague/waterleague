"""다운로드한 관망 묶음의 동일 엔진·입력 재생. 새 출력 폴더만 사용."""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import platform


def observed_run(engine, paths, metrics):
    engine.swmm_open.argtypes = [ctypes.c_char_p] * 3
    engine.wl_metricsBegin.argtypes = [ctypes.c_double, ctypes.c_double, ctypes.POINTER(ctypes.c_int), ctypes.c_int]
    engine.swmm_getIndex.argtypes = [ctypes.c_int, ctypes.c_char_p]
    engine.wl_networkAdvance.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_double)]
    engine.wl_metricsRead.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_double), ctypes.c_int]
    spec = metrics['specification']
    def check(status):
        if status != 0:
            raise ValueError('WATERSHED_REPLAY_ENGINE_FAILED')
    try:
        check(engine.swmm_open(*(os.fsencode(p) for p in paths)))
        check(engine.swmm_start(1))
        check(engine.wl_networkBegin())
        ids = spec['networkOutfalls']
        indexes = (ctypes.c_int * len(ids))(*(engine.swmm_getIndex(2, n.encode()) for n in ids))
        check(engine.wl_metricsBegin(spec['startMilliseconds']/1000, spec['endMilliseconds']/1000, indexes, len(ids)))
        elapsed = ctypes.c_double()
        for _ in range(20_000_000):
            check(engine.wl_networkAdvance(0, ctypes.byref(elapsed)))
            if elapsed.value == 0:
                break
        else:
            raise ValueError('WATERSHED_REPLAY_STEP_LIMIT')
        fields = ('outwardVolumeM3', 'inwardVolumeM3', 'peakOutwardM3s', 'peakInwardM3s',
                  'peakOutwardTimeSeconds', 'peakInwardTimeSeconds', 'coveredSeconds', 'nativeSteps')
        rows = []
        for i in range(len(ids)+1):
            raw = (ctypes.c_double * 8)()
            check(engine.wl_metricsRead(i, raw, 8))
            rows.append(dict(zip(fields, raw)))
        check(engine.swmm_end())
        check(engine.swmm_report())
        return dict(zip(ids, rows[:-1])) == metrics['outfalls'] and rows[-1] == metrics['combined']
    finally:
        engine.wl_metricsRelease()
        engine.wl_networkRelease()
        engine.swmm_close()


def replay(bundle, destination):
    bundle=Path(bundle).resolve()
    destination=Path(destination).resolve()
    result=json.loads((bundle/'result.json').read_text())
    expected=result['artifactFiles']
    for name in ('engine.bin','baseline/network.inp','strategy/network.inp',
                 'baseline/network.out','strategy/network.out'):
        path=bundle/name
        if path.is_symlink() or path.resolve()!=path or hashlib.sha256(path.read_bytes()).hexdigest()!=expected[name]:
            raise ValueError('WATERSHED_REPLAY_SOURCE_CHANGED')
    if result['engine']['platform']!=platform.platform():
        raise ValueError('WATERSHED_REPLAY_PLATFORM_MISMATCH')
    destination.mkdir(parents=True,exist_ok=False)
    engine=ctypes.CDLL(str(bundle/'engine.bin'))
    engine.swmm_run.argtypes=[ctypes.c_char_p,ctypes.c_char_p,ctypes.c_char_p]
    engine.swmm_run.restype=ctypes.c_int
    rows=[]
    for name in ('baseline','strategy'):
        target=destination/name;target.mkdir()
        source=target/'network.inp';source.write_bytes((bundle/name/'network.inp').read_bytes())
        paths=[target/('network.'+ext) for ext in ('inp','rpt','out')]
        if any(len(os.fsencode(p))>259 for p in paths): raise ValueError('WATERSHED_REPLAY_PATH_TOO_LONG')
        case = next(c for c in result['cases'] if c['id'] == name)
        metrics = case.get('evaluationMetrics')
        if metrics:
            metrics_equal = observed_run(engine, paths, metrics)
        else:
            status=engine.swmm_run(*(os.fsencode(p) for p in paths))
            if status!=0: raise ValueError('WATERSHED_REPLAY_ENGINE_FAILED')
        sha=hashlib.sha256(paths[2].read_bytes()).hexdigest()
        rows.append({'id':name,'outSha256':sha,'binaryEqual':sha==expected[name+'/network.out']})
        if metrics:
            rows[-1]['metricsEqual'] = metrics_equal
    (destination/'replay.json').write_text(json.dumps(rows,indent=2)+'\n')
    if not all(r['binaryEqual'] and r.get('metricsEqual', True) for r in rows): raise ValueError('WATERSHED_REPLAY_DIFFERENT')
    return rows


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(replay(Path(__file__).parent,args.output)))
