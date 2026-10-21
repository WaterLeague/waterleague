import { z } from 'zod';
import {
  exactOrder,
  exactScore,
  scoreContextDto,
  scorePolicyDto,
  sha256,
} from '../../evaluation/dto/scorePolicyDto';
const amount = z.number().finite();
export const historicalSubmissionDto = z
  .object({
    id: z.uuid(),
    state: z.enum(['QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED', 'REJECTED']),
    createdAt: z.iso.datetime(),
    placementCount: z.number().int().min(1).max(50),
    designRevision: z.number().int().positive().nullish(),
    message: z.string(),
    result: z
      .object({
        submissionPolicy: z.literal('FULL_EVENT_INDEPENDENT_SURFACES_V1'),
        rulesHash: sha256,
        start: z.iso.datetime({ offset: true }),
        end: z.iso.datetime({ offset: true }),
        differenceM3: amount,
        baselineAccountedM3: amount,
        designAccountedM3: amount,
        assumptions: z.array(z.string()),
        rankingStatus: z.enum(['COMPARABLE', 'COMPARISON_CONTEXT_MISSING']),
        rankingScoreM3Exact: exactScore(18).nullish(),
        scoreContext: scoreContextDto.nullish(),
      })
      .refine(
        (v) =>
          Date.parse(v.start) < Date.parse(v.end) &&
          (v.rankingStatus === 'COMPARABLE'
            ? v.scoreContext?.mode === 'SUBMISSION' &&
              v.scoreContext.binding === v.rulesHash &&
              v.rankingScoreM3Exact != null &&
              Math.abs(Number(v.rankingScoreM3Exact) - v.differenceM3) <=
                5e-19 + Number.EPSILON * Math.abs(v.differenceM3)
            : v.scoreContext == null && v.rankingScoreM3Exact == null),
        { message: '제출 평가 조건·원 지표 불일치' }
      )
      .nullable(),
  })
  .refine((v) => (v.state === 'SUCCEEDED') === (v.result !== null), {
    message: '제출 완료 상태 불일치',
  });
const entry = z
  .object({
    id: z.uuid(),
    displayName: z.string(),
    rank: z.number().int().positive(),
    differenceM3: amount,
    differenceM3Exact: exactScore(18),
    costKrw: amount.nonnegative(),
    submittedAt: z.iso.datetime(),
    rulesHash: sha256,
    scorePolicySha256: sha256,
    comparisonGroupHash: sha256,
  })
  .refine((v) => Number(v.differenceM3Exact) === v.differenceM3, {
    message: '순위 원장의 정확한 체적 불일치',
  });
const group = z
  .object({
    rulesHash: sha256,
    comparisonGroupHash: sha256,
    scorePolicySha256: sha256,
    entries: z.array(entry).min(1).max(100),
  })
  .superRefine((v, ctx) => {
    let lastRank = 0;
    for (const [i, e] of v.entries.entries()) {
      const previous = v.entries[i - 1];
      const expectedRank =
        previous && exactOrder(previous.differenceM3Exact, e.differenceM3Exact) === 0
          ? lastRank
          : i + 1;
      if (
        e.rulesHash !== v.rulesHash ||
        e.comparisonGroupHash !== v.comparisonGroupHash ||
        e.scorePolicySha256 !== v.scorePolicySha256 ||
        e.rank !== expectedRank ||
        (previous && exactOrder(previous.differenceM3Exact, e.differenceM3Exact) < 0)
      )
        ctx.addIssue({ code: 'custom', message: '다른 평가 조건·순위·체적 순서 혼합' });
      lastRank = e.rank;
    }
  });
export const historicalBoardDto = z
  .object({
    eventId: z.string(),
    title: z.string(),
    policy: z.literal('FULL_EVENT_INDEPENDENT_SURFACES_V1'),
    modelGrade: z.literal('CURRENT_GEOMETRY_HISTORICAL_RAINFALL_STRESS_TEST'),
    scorePolicy: scorePolicyDto,
    withheldSubmissionCount: z.number().int().nonnegative(),
    groups: z.array(group),
    ownEntries: z.array(entry).optional(),
  })
  .refine(
    (v) =>
      new Set(v.groups.map((g) => `${g.rulesHash}:${g.comparisonGroupHash}`)).size ===
      v.groups.length,
    { message: '비교 집단 중복' }
  );
