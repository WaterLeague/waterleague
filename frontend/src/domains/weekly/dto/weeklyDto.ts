import { z } from 'zod';
import { exactScore, scorePolicyDto, sha256 } from '../../evaluation/dto/scorePolicyDto';
const contribution = {
  rank: z.number().int().positive().nullable(),
  scoreM3: z.number().finite().nullable(),
  scoreM3Exact: exactScore(9).nullable(),
  evaluatedMinutes: z.number().int().nonnegative(),
  evaluatedSeconds: z.number().int().nonnegative().optional(),
  expectedMinutes: z.number().int().nonnegative(),
  expectedSeconds: z.number().int().nonnegative().optional(),
};
const computed = (v: {
  scoreM3: number | null;
  scoreM3Exact: string | null;
  rank: number | null;
  evaluatedSeconds?: number;
  evaluatedMinutes: number;
}) =>
  v.scoreM3 === null
    ? v.scoreM3Exact === null && v.rank === null
    : v.scoreM3Exact !== null &&
      Number(v.scoreM3Exact) === v.scoreM3 &&
      v.rank !== null &&
      (v.evaluatedSeconds ?? v.evaluatedMinutes * 60) > 0;
const player = z
  .object({ ...contribution, playerId: z.uuid(), nickname: z.string(), districtId: z.string() })
  .refine(computed, { message: '평가 원장·점수·순위 불일치' });
const period = z
  .object({
    weekStart: z.iso.date(),
    startsAt: z.iso.datetime(),
    endsAt: z.iso.datetime(),
    evaluatedTarget: z.iso.datetime(),
    status: z.enum(['EMPTY', 'IN_PROGRESS', 'PROVISIONAL', 'FINAL', 'WITHHELD']),
    comparisonStatus: z.enum(['COMPARABLE', 'UNAVAILABLE', 'WITHHELD']),
    comparisonReason: z
      .enum(['NO_EVALUATED_RECORDS', 'COMPARISON_CONTEXT_MISSING', 'MIXED_COMPARISON_CONTEXTS'])
      .nullable(),
    comparisonGroupHash: sha256.nullable(),
    evaluatedMinutes: z.number().int().nonnegative(),
    evaluatedSeconds: z.number().int().nonnegative().optional(),
    expectedMinutes: z.number().int().nonnegative(),
    expectedSeconds: z.number().int().nonnegative().optional(),
    districts: z
      .array(
        z
          .object({ ...contribution, districtId: z.string(), districtName: z.string() })
          .refine(computed, { message: '평가 원장·점수·순위 불일치' })
      )
      .length(25),
    players: z.array(player).max(100),
    participantCount: z.number().int().nonnegative(),
    own: player.nullable(),
    winnerDistrictIds: z.array(z.string()),
  })
  .superRefine((v, ctx) => {
    const seconds = v.evaluatedSeconds ?? v.evaluatedMinutes * 60;
    const rows = [...v.districts, ...v.players, ...(v.own ? [v.own] : [])];
    const valid =
      v.comparisonStatus === 'COMPARABLE'
        ? seconds > 0 &&
          v.comparisonGroupHash !== null &&
          v.comparisonReason === null &&
          v.status !== 'WITHHELD' &&
          rows.every(
            (r) => (r.scoreM3 === null) === ((r.evaluatedSeconds ?? r.evaluatedMinutes * 60) === 0)
          )
        : v.comparisonGroupHash === null &&
          rows.every((r) => r.scoreM3 === null && r.rank === null) &&
          v.winnerDistrictIds.length === 0 &&
          (v.comparisonStatus === 'WITHHELD'
            ? v.status === 'WITHHELD' &&
              seconds > 0 &&
              ['COMPARISON_CONTEXT_MISSING', 'MIXED_COMPARISON_CONTEXTS'].includes(
                v.comparisonReason ?? ''
              )
            : v.status !== 'WITHHELD' &&
              seconds === 0 &&
              v.comparisonReason === 'NO_EVALUATED_RECORDS');
    if (!valid) ctx.addIssue({ code: 'custom', message: '주간 평가 조건·합산 상태 불일치' });
  });
export const weeklyDto = z.object({
  generatedAt: z.iso.datetime(),
  ruleVersion: z.enum(['OBSERVED_ACCOUNTED_VOLUME_V1', 'OBSERVED_ACCOUNTED_VOLUME_SECONDS_V2']),
  validationLevel: z.literal('EXPLORATORY'),
  scorePolicy: scorePolicyDto,
  current: period,
  previous: period,
});
export type WeeklySnapshot = z.infer<typeof weeklyDto>;
