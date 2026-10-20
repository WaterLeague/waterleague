"""공개 계산 코드와 고정 입력 정책의 평가 버전 생성·검사."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'simulation'))
from waterleague_sim.evaluation.score_policy import POLICY_FILE, encode, source_policy


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    raw = encode(source_policy())
    if args.check:
        if not POLICY_FILE.is_file() or POLICY_FILE.read_bytes() != raw:
            raise SystemExit('평가 코드·자료 변경 후 고정 정책 재생성 필요')
        print('평가 코드·자료 정책 일치')
    else:
        POLICY_FILE.parent.mkdir(parents=True, exist_ok=True)
        POLICY_FILE.write_bytes(raw)


if __name__ == '__main__':
    main()
