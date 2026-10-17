import { z } from 'zod';
export const budgetDto = z.object({
  policy: z.object({
    limitKrw: z.number().positive(),
    districtLimitKrw: z.number().positive(),
    districtCount: z.number().int().positive(),
    referenceYear: z.number().int(),
    sourceTitle: z.string(),
    sourceUrl: z.url().startsWith('https://'),
    sourceSha256: z.string().regex(/^[a-f0-9]{64}$/),
    ruleVersion: z.string(),
    note: z.string(),
  }),
  districts: z
    .array(
      z.object({
        districtId: z.string(),
        districtName: z.string(),
        allocatedKrw: z.number().nonnegative(),
        remainingKrw: z.number().nonnegative(),
      })
    )
    .length(25),
  allocatedKrw: z.number().nonnegative(),
  remainingKrw: z.number().nonnegative(),
});
export type Budget = z.infer<typeof budgetDto>;
