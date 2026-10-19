"""전체 시뮬레이션 회귀 시험을 파일 단위로 빠짐없이 분할 실행."""
import argparse
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--shard', type=int, default=0)
    parser.add_argument('--shards', type=int, default=1)
    args = parser.parse_args()
    if not 0 <= args.shard < args.shards <= 16:
        parser.error('시험 분할 범위 오류')
    modules = sorted((ROOT / 'simulation/tests').glob('test_*.py'))[args.shard::args.shards]
    env = os.environ | {'PYTHONPATH': os.pathsep.join([str(ROOT), str(ROOT / 'simulation')])}
    print(f'shard {args.shard + 1}/{args.shards}: {len(modules)} modules', flush=True)
    failed = []
    for module in modules:
        # EPA와 ANUGA의 네이티브 런타임이 다른 시험 모듈에 잔류하지 않게 한다.
        try:
            result = subprocess.run([sys.executable, '-m', 'unittest', 'discover',
                '-s', 'simulation/tests', '-p', module.name, '-v'], cwd=ROOT, env=env, timeout=900)
            if result.returncode:
                failed.append(module.name)
        except subprocess.TimeoutExpired:
            failed.append(module.name)
    print(f'failed modules: {failed}', flush=True)
    raise SystemExit(1 if failed else 0)


if __name__ == '__main__':
    main()
