import { z } from 'zod';
const contribution = {
  rank: z.number().int().positive().nullable(),
  scoreM3: z.number().finite(),
  evaluatedMinutes: z.number().int().nonnegative(),
  evaluatedSeconds: z.number().int().nonnegative().optional(),
  expectedMinutes: z.number().int().nonnegative(),
  expectedSeconds: z.number().int().nonnegative().optional(),
};
const player = z.object({
  ...contribution,
  playerId: z.uuid(),
  nickname: z.string(),
  districtId: z.string(),
});
const period = z.object({
  weekStart: z.iso.date(),
  startsAt: z.iso.datetime(),
  endsAt: z.iso.datetime(),
  evaluatedTarget: z.iso.datetime(),
  status: z.enum(['EMPTY', 'IN_PROGRESS', 'PROVISIONAL', 'FINAL']),
  evaluatedMinutes: z.number().int().nonnegative(),
  evaluatedSeconds: z.number().int().nonnegative().optional(),
  expectedMinutes: z.number().int().nonnegative(),
  expectedSeconds: z.number().int().nonnegative().optional(),
  districts: z
    .array(z.object({ ...contribution, districtId: z.string(), districtName: z.string() }))
    .length(25),
  players: z.array(player).max(100),
  participantCount: z.number().int().nonnegative(),
  own: player.nullable(),
  winnerDistrictIds: z.array(z.string()),
});
export const weeklyDto = z.object({
  generatedAt: z.iso.datetime(),
  ruleVersion: z.enum(['OBSERVED_ACCOUNTED_VOLUME_V1', 'OBSERVED_ACCOUNTED_VOLUME_SECONDS_V2']),
  validationLevel: z.literal('EXPLORATORY'),
  current: period,
  previous: period,
});
export type WeeklySnapshot = z.infer<typeof weeklyDto>;
