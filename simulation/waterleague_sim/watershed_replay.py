"""다운로드한 관망 묶음의 동일 엔진·입력 재생. 새 출력 폴더만 사용."""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import platform


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
        status=engine.swmm_run(*(os.fsencode(p) for p in paths))
        if status!=0: raise ValueError('WATERSHED_REPLAY_ENGINE_FAILED')
        sha=hashlib.sha256(paths[2].read_bytes()).hexdigest()
        rows.append({'id':name,'outSha256':sha,'binaryEqual':sha==expected[name+'/network.out']})
    (destination/'replay.json').write_text(json.dumps(rows,indent=2)+'\n')
    if not all(r['binaryEqual'] for r in rows): raise ValueError('WATERSHED_REPLAY_DIFFERENT')
    return rows


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(replay(Path(__file__).parent,args.output)))
