import { z } from 'zod';
export const budgetDto = z.object({
  policy: z.object({
    limitKrw: z.number().positive(),
    personalLimitKrw: z.number().positive(),
    allocationScope: z.literal('MEMBER'),
    referenceYear: z.number().int(),
    sourceTitle: z.string(),
    sourceUrl: z.url().startsWith('https://'),
    sourceSha256: z.string().regex(/^[a-f0-9]{64}$/),
    ruleVersion: z.literal('SEOUL_PERSONAL_FULL_2026_V3'),
    note: z.string(),
  }),
  allocatedKrw: z.number().nonnegative(),
  remainingKrw: z.number().nonnegative(),
  personal: z.boolean(),
});
export type Budget = z.infer<typeof budgetDto>;
