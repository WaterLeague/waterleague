"""회원 계산과 분리된 공개 기준안 워커. 고정 모형이 없으면 조회·계산 없음."""
import argparse
import os
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'simulation'))
from waterleague_sim.public_surface.service import run_once
from waterleague_sim.engine.flood_errors import FloodModelError


def main():
    from local_config import load
    parser=argparse.ArgumentParser()
    parser.add_argument('--once',action='store_true')
    args=parser.parse_args()
    load();os.umask(0o077)
    artifacts=Path(os.environ.get('ARTIFACTS_PATH',ROOT/'data/runs')).resolve()
    while True:
        try:
            worked=run_once(artifacts)
            if worked:print('공개 기준안 처리 완료',flush=True)
        except (FloodModelError,OSError,ValueError):
            print('PUBLIC_SURFACE_WORKER_FAILED',file=sys.stderr,flush=True)
            if args.once:raise SystemExit(1) from None
        if args.once:return
        time.sleep(10)


if __name__=='__main__':main()
