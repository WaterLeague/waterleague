import { z } from 'zod';
export const sha256 = z.string().regex(/^[a-f0-9]{64}$/);
export const scorePolicyDto = z.object({
  sha256,
  version: z.literal('ABSOLUTE_ACCOUNTED_VOLUME_RANKING_V1'),
  metric: z.literal('surfaceAccountedVolumeM3'),
  unit: z.literal('m3'),
  direction: z.literal('HIGHER_SIGNED_IMPROVEMENT_IS_BETTER'),
  scope: z.literal('SELECTED_INDEPENDENT_SURFACES_ONLY'),
  rounding: z.literal('HALF_EVEN'),
  weeklyDecimalPlaces: z.literal(9),
  submissionDecimalPlaces: z.literal(18),
  tie: z.literal('EXACT_STORED_DECIMAL_EQUALITY'),
  rank: z.literal('COMPETITION_1_1_3'),
  weeklyPlayerTieOrder: z.tuple([z.literal('playerId')]),
  weeklyDistrictTieOrder: z.tuple([z.literal('districtName'), z.literal('districtId')]),
  submissionTieOrder: z.tuple([z.literal('submittedAt'), z.literal('id')]),
  relativeUsedForRanking: z.literal(false),
  compositeScore: z.null(),
  missingPolicy: z.literal('UNAVAILABLE_WITH_REASON_NO_ZERO_OR_REDISTRIBUTION'),
  weeklyWindow: z.literal('KST_MONDAY_INSTALLATION_AFTER_CONFIRMED_OBSERVATION'),
  submissionWindow: z.literal('FULL_EVENT_AFTER_ANTECEDENT'),
  cohort: z.literal('POLICY_RUNTIME_TEMPORAL_RULE_AND_FROZEN_EVENT_RULES'),
});
export const scoreContextDto = z.object({
  sha256,
  version: z.literal('ABSOLUTE_ACCOUNTED_VOLUME_RANKING_V1'),
  policySha256: sha256,
  mode: z.enum(['WEEKLY', 'SUBMISSION']),
  binding: z.string().min(1),
  runtime: z.object({
    engine: z.object({ engineVersion: z.literal('5.2.4'), binarySha256: sha256 }).passthrough(),
    python: z.string().min(1),
    system: z.string().min(1),
    machine: z.string().min(1),
    packages: z.object({ pyproj: z.string().min(1), shapely: z.string().min(1) }),
  }),
});
export const exactScore = (places: number) =>
  z.string().regex(new RegExp(`^-?(0|[1-9]\\d{0,30})\\.\\d{${places}}$`));
export function exactOrder(a: string, b: string): number {
  const scaled = (s: string) => BigInt(s.replace('.', ''));
  return scaled(a) < scaled(b) ? -1 : scaled(a) > scaled(b) ? 1 : 0;
}
