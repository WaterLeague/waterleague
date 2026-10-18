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
export const budgetRecordEvidenceDto = z
  .object({
    schemaVersion: z.literal(1),
    calculationId: z.uuid(),
    installationId: z.uuid(),
    capturedAt: z.string().datetime({ offset: true }),
    evaluatedThrough: z.string().datetime({ offset: true }),
    status: z.enum(['AVAILABLE', 'NOT_RECORDED']),
    timeBasis: z.literal('EFFECTIVE_EVENT_TIME'),
    installationCostKrw: amount,
    allocatedAtEvaluationKrw: amount.nullable(),
    allocatedAtCaptureKrw: amount.nullable(),
    removedAt: z.string().datetime({ offset: true }).nullable(),
    entries: budgetLedgerDto.shape.entries.max(2),
  })
  .refine(
    (value) =>
      value.status === 'AVAILABLE'
        ? value.entries.length > 0 &&
          value.allocatedAtEvaluationKrw !== null &&
          value.allocatedAtCaptureKrw !== null
        : value.entries.length === 0 &&
          value.allocatedAtEvaluationKrw === null &&
          value.allocatedAtCaptureKrw === null,
    { message: '예산 원장 상태와 기록 불일치' }
  );
export type BudgetRecordEvidence = z.infer<typeof budgetRecordEvidenceDto>;
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
