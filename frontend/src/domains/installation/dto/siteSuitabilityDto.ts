import { z } from 'zod';

export const eligibilityDto = z.enum(['ELIGIBLE', 'CONDITIONAL', 'PROHIBITED', 'UNKNOWN']);
const priority = ['PROHIBITED', 'CONDITIONAL', 'UNKNOWN', 'ELIGIBLE'];
export const conditionIds = {
  GROUND: ['SOIL', 'SLOPE', 'GROUNDWATER', 'UNDERGROUND_UTILITIES', 'TRAFFIC_LOAD', 'DRAINAGE'],
  ROOF: ['SLOPE', 'ROOF_STRUCTURAL_LOAD', 'WATERPROOFING', 'DRAINAGE'],
} as const;
const evidenceDto = z.strictObject({
  title: z.string().trim().min(1).max(300),
  url: z
    .url({ protocol: /^https$/ })
    .max(2000)
    .refine((value) => {
      const url = new URL(value);
      return !url.username && !url.password && !/\s/.test(value);
    }),
  sha256: z.string().regex(/^[a-f0-9]{64}$/),
  reference: z.string().trim().min(1).max(500),
});
export const siteSuitabilityDto = z
  .strictObject({
    version: z.literal('SITE_SUITABILITY_V1'),
    policySha256: z.string().regex(/^[a-f0-9]{64}$/),
    status: eligibilityDto,
    explorationAllowed: z.boolean(),
    constructionApproved: z.literal(false),
    checks: z
      .array(
        z
          .strictObject({
            id: z.enum([
              'SOIL',
              'SLOPE',
              'GROUNDWATER',
              'UNDERGROUND_UTILITIES',
              'TRAFFIC_LOAD',
              'ROOF_STRUCTURAL_LOAD',
              'WATERPROOFING',
              'DRAINAGE',
            ]),
            status: eligibilityDto,
            reason: z.string().trim().min(1).max(500),
            evidence: evidenceDto.nullable(),
          })
          .refine((row) => row.status === 'UNKNOWN' || row.evidence !== null)
      )
      .min(4)
      .max(6),
  })
  .refine((value) => {
    const ids = value.checks.map((row) => row.id);
    return (
      new Set(ids).size === ids.length &&
      Object.values(conditionIds).some(
        (required) => required.length === ids.length && required.every((id) => ids.includes(id))
      ) &&
      value.explorationAllowed === ['ELIGIBLE', 'UNKNOWN'].includes(value.status) &&
      value.checks.every((row) => priority.indexOf(value.status) <= priority.indexOf(row.status))
    );
  });
export type SiteSuitability = z.infer<typeof siteSuitabilityDto>;
