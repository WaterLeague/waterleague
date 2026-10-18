import { z } from 'zod';
const facilityType = z.enum(['RAIN_GARDEN', 'PERMEABLE_PAVEMENT', 'GREEN_ROOF']);
const amount = z.number().finite().nonnegative();
export const budgetAccountingDto = z.object({
  version: z.string(),
  programs: z.array(
    z.object({
      id: z.string(),
      name: z.string(),
      limitKrw: amount,
      allocatedKrw: amount,
      remainingKrw: amount,
      sourceSha256: z.string().regex(/^[a-f0-9]{64}$/),
    })
  ),
  facilities: z.array(
    z.object({
      facilityType,
      programId: z.string(),
      limitKrw: amount.nullable(),
      allocatedKrw: amount,
      availableKrw: amount,
    })
  ),
});
export type BudgetAccounting = z.infer<typeof budgetAccountingDto>;
export const budgetLedgerDto = z.object({
  entries: z.array(
    z.object({
      id: z.string().regex(/^[1-9][0-9]*$/),
      installationId: z.uuid(),
      programId: z.string(),
      facilityType,
      eventType: z.enum(['ALLOCATE', 'RELEASE']),
      amountKrw: amount.positive(),
      effectiveAt: z.string(),
      recordedAt: z.string(),
      provenance: z.enum(['LEGACY_IMPORT', 'LIVE_TRANSACTION']),
      accountingVersion: z.string(),
      sourceBudgetPolicy: z.unknown().nullable(),
    })
  ),
  nextBeforeId: z
    .string()
    .regex(/^[1-9][0-9]*$/)
    .nullable(),
});
export type BudgetLedger = z.infer<typeof budgetLedgerDto>;
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
  accounting: budgetAccountingDto,
});
export type Budget = z.infer<typeof budgetDto>;
