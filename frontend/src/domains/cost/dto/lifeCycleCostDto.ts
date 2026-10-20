import { z } from 'zod';
const hash = z.string().regex(/^[a-f0-9]{64}$/);
const money = z.string().regex(/^-?(0|[1-9]\d{0,35})\.\d{2}$/);
const scaled = (v: string) => BigInt(v.replace('.', ''));
const sum = (values: string[]) => values.reduce((a, v) => a + scaled(v), 0n);
const category = z.enum([
  'INITIAL',
  'OPERATION',
  'INSPECTION_CLEANING',
  'REPAIR',
  'REPLACEMENT',
  'DISPOSAL',
  'RESIDUAL',
]);
const rate = z
  .string()
  .regex(/^-?(0|[1-9]\d*)(\.\d{1,12})?$/)
  .refine((v) => Number(v) > -1 && Number(v) <= 1);
export const lifeCycleCostDto = z
  .object({
    version: z.literal('DISCOUNTED_CASH_FLOW_V1'),
    scenarioId: z.string().min(1),
    status: z.enum(['COMPLETE', 'PARTIAL', 'UNAVAILABLE']),
    currency: z.enum(['KRW', 'USD']),
    studyPeriodYears: z.number().int().min(1).max(100).nullable(),
    priceBaseYear: z.number().int().min(1900).max(2200).nullable(),
    priceBasis: z.enum(['CONSTANT', 'CURRENT']),
    discountKind: z.enum(['REAL', 'NOMINAL']).nullable(),
    discountRates: z.array(rate).max(100).nullable(),
    functionalUnit: z.string(),
    classification: z.string(),
    timing: z.literal('INITIAL_AT_YEAR_ZERO_END_OF_YEAR'),
    precision: z.literal('DECIMAL_50_SUM_THEN_HALF_EVEN_2'),
    planSha256: hash,
    policySha256: hash,
    comparisonKey: hash.nullable(),
    lifeCycleCost: money.nullable(),
    knownPresentValue: money.nullable(),
    annualRoundingDifference: money.nullable(),
    categoryRoundingDifference: money.nullable(),
    missingInputs: z.array(z.string()).max(30),
    categories: z
      .array(
        z.object({
          id: category,
          coverage: z.enum(['COMPLETE', 'PARTIAL', 'UNPRICED', 'NOT_APPLICABLE']),
          presentValue: money.nullable(),
        })
      )
      .length(7),
    annualCashflows: z
      .array(
        z.object({
          year: z.number().int().min(0).max(100),
          cost: money,
          credit: money,
          presentValue: money,
        })
      )
      .max(101),
    termsEvidence: z.object({ sha256: hash, reference: z.string().min(1) }),
    limitations: z.array(z.string()),
    budgetChargeChanged: z.literal(false),
    physicalEffectAnnualized: z.literal(false),
    scoreUsed: z.literal(false),
    sensitivity: z
      .array(
        z.object({
          id: z.string(),
          label: z.string(),
          rate,
          knownPresentValue: money.nullable(),
          lifeCycleCost: money.nullable(),
          status: z.enum(['PARTIAL', 'UNAVAILABLE', 'COMPLETE']),
          planSha256: hash,
        })
      )
      .max(10)
      .optional(),
  })
  .superRefine((v, ctx) => {
    const unavailable = v.status === 'UNAVAILABLE';
    const financial =
      v.studyPeriodYears !== null &&
      v.discountRates?.length === v.studyPeriodYears &&
      v.discountKind !== null;
    const complete = v.status === 'COMPLETE';
    const categories = v.categories;
    const valid =
      new Set(categories.map((c) => c.id)).size === 7 &&
      (v.discountKind !== 'REAL' || v.priceBasis === 'CONSTANT') &&
      (v.discountKind !== 'NOMINAL' || v.priceBasis === 'CURRENT') &&
      (v.discountRates === null || v.discountRates.length === v.studyPeriodYears) &&
      (complete
        ? financial &&
          v.priceBaseYear !== null &&
          v.missingInputs.length === 0 &&
          v.comparisonKey !== null &&
          v.lifeCycleCost !== null &&
          v.lifeCycleCost === v.knownPresentValue &&
          categories.every((c) => ['COMPLETE', 'NOT_APPLICABLE'].includes(c.coverage))
        : v.lifeCycleCost === null && v.comparisonKey === null && v.missingInputs.length > 0) &&
      (unavailable
        ? v.knownPresentValue === null &&
          v.annualRoundingDifference === null &&
          v.categoryRoundingDifference === null &&
          v.annualCashflows.length === 0
        : financial &&
          v.knownPresentValue !== null &&
          v.annualRoundingDifference !== null &&
          v.categoryRoundingDifference !== null &&
          sum(v.annualCashflows.map((c) => c.presentValue)) + scaled(v.annualRoundingDifference) ===
            scaled(v.knownPresentValue) &&
          sum(categories.flatMap((c) => (c.presentValue === null ? [] : [c.presentValue]))) +
            scaled(v.categoryRoundingDifference) ===
            scaled(v.knownPresentValue)) &&
      categories.every((c) =>
        c.coverage === 'UNPRICED'
          ? c.presentValue === null
          : c.coverage === 'NOT_APPLICABLE'
            ? c.presentValue === '0.00'
            : c.presentValue === null
              ? unavailable
              : c.id === 'RESIDUAL'
                ? scaled(c.presentValue) <= 0n
                : scaled(c.presentValue) >= 0n
      ) &&
      new Set(v.annualCashflows.map((c) => c.year)).size === v.annualCashflows.length &&
      (!v.sensitivity ||
        (new Set(v.sensitivity.map((s) => s.id)).size === v.sensitivity.length &&
          v.sensitivity.every((s) =>
            s.status === 'COMPLETE'
              ? s.lifeCycleCost !== null && s.lifeCycleCost === s.knownPresentValue
              : s.lifeCycleCost === null &&
                (s.status === 'UNAVAILABLE'
                  ? s.knownPresentValue === null
                  : s.knownPresentValue !== null)
          ))) &&
      v.annualCashflows.every(
        (c, i) =>
          c.year <= (v.studyPeriodYears ?? 0) &&
          scaled(c.cost) >= 0n &&
          scaled(c.credit) >= 0n &&
          (i === 0 || v.annualCashflows[i - 1].year < c.year)
      );
    if (!valid) ctx.addIssue({ code: 'custom', message: '생애비용 상태·기간·원장 합계 불일치' });
  });
export type LifeCycleCost = z.infer<typeof lifeCycleCostDto>;
export const cisternLifeCycleCostsDto = z
  .object({
    version: z.literal('DISCOUNTED_CASH_FLOW_V1'),
    catalogHash: hash,
    policySha256: hash,
    items: z
      .array(
        z.object({
          placementId: z.string(),
          quotes: z
            .array(z.object({ id: z.enum(['A', 'B', 'C']), report: lifeCycleCostDto }))
            .max(3),
        })
      )
      .min(1)
      .max(20),
  })
  .refine(
    (v) =>
      new Set(v.items.map((i) => i.placementId)).size === v.items.length &&
      v.items.every(
        (i) =>
          new Set(i.quotes.map((q) => q.id)).size === i.quotes.length &&
          i.quotes.every((q) => q.report.policySha256 === v.policySha256)
      ),
    { message: '이용조 생애비용 집단 불일치' }
  );
export type CisternLifeCycleCosts = z.infer<typeof cisternLifeCycleCostsDto>;
