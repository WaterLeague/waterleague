"""생성 계보 JSON과 모델 원문으로 학습 분포·후보·예산·hash 독립 검증."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'simulation'))
from waterleague_sim.optimization.replay import decoded, verify


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('provenance', type=Path)
    parser.add_argument('--model', type=Path, required=True)
    args = parser.parse_args()
    if args.provenance.stat().st_size > 8 * 1024 * 1024 or args.model.stat().st_size > 2 * 1024 * 1024:
        raise SystemExit('입력 크기 상한 초과')
    try:
        report = verify(args.model.read_bytes(), decoded(args.provenance.read_bytes()))
    except (ValueError, KeyError, TypeError) as error:
        raise SystemExit('생성 계보 검증 실패: ' + str(error)) from None
    print(f"원본 {report['requestedCount']}개·고유 {report['uniquePhysicalCount']}개·학습 {report['trainingCount']}개·후보 {len(report['candidates'])}개 재생 일치")
    print('검증 범위: 생성 규칙·입력/출력 내부 일관성. 원본 동의·서버 진본성·현장 성능 인증 아님')


if __name__ == '__main__':
    main()
