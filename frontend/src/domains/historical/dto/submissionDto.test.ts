import { expect, it } from 'vitest';
import sourcePolicy from '../../../../../backend/src/main/resources/evaluation/game-score-policy-v1.json';
import { historicalBoardDto, historicalSubmissionDto } from './submissionDto';
import actualBoard from '../../physics/view/fixtures/score-policy-board-http-v1.json';
import actualOne from '../../physics/view/fixtures/score-policy-submission-http-1-v1.json';
import actualTwo from '../../physics/view/fixtures/score-policy-submission-http-2-v1.json';
import actualThree from '../../physics/view/fixtures/score-policy-submission-http-3-v1.json';
const rulesHash = 'a'.repeat(64),
  comparisonGroupHash = 'b'.repeat(64),
  scorePolicySha256 = 'c'.repeat(64);
const scorePolicy = { ...sourcePolicy, sha256: scorePolicySha256 };
it('실제 회원 HTTP 제출·최고 기록의 정확한 원장과 계산 조건 결속', () => {
  const board = historicalBoardDto.parse(actualBoard.value);
  const records = [actualOne, actualTwo, actualThree].map((v) =>
    historicalSubmissionDto.parse(v.value)
  );
  expect(records.every((v) => v.result?.rankingStatus === 'COMPARABLE')).toBe(true);
  expect(board.groups[0].entries).toHaveLength(1);
  expect(board.groups[0].comparisonGroupHash).toBe(records[0].result?.scoreContext?.sha256);
  const changed = structuredClone(records[0]);
  changed.result!.scoreContext!.binding = 'd'.repeat(64);
  expect(historicalSubmissionDto.safeParse(changed).success).toBe(false);
  const missing = structuredClone(records[0]);
  missing.result!.scoreContext = null;
  expect(historicalSubmissionDto.safeParse(missing).success).toBe(false);
});
function board(scores: string[]) {
  return {
    eventId: 'test-only',
    title: '시험용 순위',
    policy: 'FULL_EVENT_INDEPENDENT_SURFACES_V1',
    modelGrade: 'CURRENT_GEOMETRY_HISTORICAL_RAINFALL_STRESS_TEST',
    scorePolicy,
    withheldSubmissionCount: 0,
    groups: [
      {
        rulesHash,
        comparisonGroupHash,
        scorePolicySha256,
        entries: scores.map((value, i) => ({
          id: `00000000-0000-4000-8000-${String(i + 1).padStart(12, '0')}`,
          displayName: '시험',
          rank: i + 1,
          differenceM3: Number(value),
          differenceM3Exact: value,
          costKrw: 0,
          submittedAt: '2026-10-20T00:00:00Z',
          rulesHash,
          comparisonGroupHash,
          scorePolicySha256,
        })),
      },
    ],
  };
}
it('숫자 변환으로 같아져도 정확한 소수의 개선 순위를 보존', () => {
  const value = board(['100000000000000.000000000000000002', '100000000000000.000000000000000001']);
  expect(value.groups[0].entries[0].differenceM3).toBe(value.groups[0].entries[1].differenceM3);
  expect(historicalBoardDto.safeParse(value).success).toBe(true);
  value.groups[0].entries[1].rank = 1;
  expect(historicalBoardDto.safeParse(value).success).toBe(false);
});
it('동점 1·1·3과 음수·0·미확인 기록 수 보존', () => {
  const value = board(['0.000000000000000000', '0.000000000000000000', '-0.000000000000000001']);
  value.groups[0].entries[1].rank = 1;
  value.withheldSubmissionCount = 2;
  expect(historicalBoardDto.parse(value).groups[0].entries.map((e) => e.rank)).toEqual([1, 1, 3]);
  value.groups[0].entries[2].rank = 2;
  expect(historicalBoardDto.safeParse(value).success).toBe(false);
});
it('다른 실행 조건·원장·규칙 혼합과 참가자 기준 정규화 거부', () => {
  const value = board(['1.000000000000000000']);
  for (const field of ['rulesHash', 'comparisonGroupHash', 'scorePolicySha256'] as const) {
    const changed = structuredClone(value);
    changed.groups[0].entries[0][field] = 'd'.repeat(64);
    expect(historicalBoardDto.safeParse(changed).success).toBe(false);
  }
  const changed = structuredClone(value);
  changed.scorePolicy.relativeUsedForRanking = true as false;
  expect(historicalBoardDto.safeParse(changed).success).toBe(false);
});
