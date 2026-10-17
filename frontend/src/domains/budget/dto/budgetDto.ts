import { z } from 'zod';
export const budgetDto = z.object({
  policy: z.object({
    limitKrw: z.number().positive(),
    referenceYear: z.number().int(),
    sourceTitle: z.string(),
    sourceUrl: z.url().startsWith('https://'),
    sourceSha256: z.string().regex(/^[a-f0-9]{64}$/),
    ruleVersion: z.string(),
    note: z.string(),
  }),
  allocatedKrw: z.number().nonnegative(),
  remainingKrw: z.number().nonnegative(),
});
export type Budget = z.infer<typeof budgetDto>;
