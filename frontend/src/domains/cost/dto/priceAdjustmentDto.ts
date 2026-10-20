import { z } from 'zod';

export const indexMethod = 'KICT_MONTHLY_INDEX_RATIO_ANNUAL_PROXY_V1';
export const indexedEvidence = 'PUBLIC_PLAN_INDEX_ADJUSTED_WITH_EXPLICIT_PRICE_PERIOD_ASSUMPTION';
const hash = z.string().regex(/^[a-f0-9]{64}$/);
const money = z.number().int().positive().max(Number.MAX_SAFE_INTEGER);
const validIndex = (v: number) =>
  Number.isFinite(v) && v > 0 && v <= 1000000 && Math.abs(v * 100 - Math.round(v * 100)) < 1e-7;
const indexCell = z.object({
  periodLabel: z.string(),
  cell: z.string().regex(/^[A-Z]+[1-9]\d*$/),
  value: z.number().positive().max(1000000).refine(validIndex),
});

export const priceAdjustmentDto = z
  .object({
    method: z.literal(indexMethod),
    currency: z.literal('KRW'),
    targetPeriod: z.literal('2026-08'),
    targetProvisional: z.literal(true),
    observedBasePriceYear: z.null(),
    assumedBasePriceYear: z.literal(2022),
    basePeriodBasis: z.literal('PUBLIC_PLAN_YEAR_ANNUAL_MEAN_PROXY_NOT_VERIFIED_QUOTE_DATE'),
    originalUnitCostKrw: money,
    adjustedUnitCostKrw: money,
    formula: z.literal('ceil(originalUnitCostKrw * targetIndex * 12 / sum(baseMonthlyIndices))'),
    rounding: z.literal('CEILING_KRW_PER_M2_FINAL_ONLY'),
    indexSeries: z.enum(['도시토목', '도로시설']),
    seriesRole: z.literal('CONSTRUCTION_TYPE_PROXY_NOT_BILL_OF_QUANTITIES_MATCH'),
    indexBaseYear: z.literal(2020),
    baseMonthlyIndices: z.array(indexCell).length(12),
    targetIndex: indexCell,
    indexSourceUrl: z.literal('https://cost.kict.re.kr/#/notice/file/detail/47229'),
    indexPublishedAt: z.literal('2026-09-30'),
    indexManifestSha256: hash,
    indexWorkbookSha256: hash,
    baseMonthSensitivityKrwPerM2: z.tuple([money, money]),
    sensitivityMeaning: z.literal(
      '2022_MONTH_CHOICE_ONLY_NOT_MARKET_PRICE_RANGE_OR_CONFIDENCE_INTERVAL'
    ),
  })
  .refine((v) => {
    if (
      !Number.isSafeInteger(v.originalUnitCostKrw) ||
      !Number.isSafeInteger(v.adjustedUnitCostKrw)
    )
      return false;
    const months = v.baseMonthlyIndices;
    if (
      months.length !== 12 ||
      !months.every((m) => validIndex(m.value)) ||
      !validIndex(v.targetIndex.value) ||
      !months.every((m, i) => m.periodLabel === `2022년 ${i + 1}월`) ||
      v.targetIndex.periodLabel !== '2026년 8월\n(잠정)'
    )
      return false;
    // 지수의 소수 두 자리를 정수로 바꿔 최종 원화 올림 경계를 보존한다.
    const scaled = months.map((m) => BigInt(Math.round(m.value * 100)));
    if (scaled.some((n) => n <= 0n)) return false;
    const numerator = BigInt(v.originalUnitCostKrw) * BigInt(Math.round(v.targetIndex.value * 100));
    const ceil = (a: bigint, b: bigint) => (a + b - 1n) / b;
    const sum = scaled.reduce((a, b) => a + b, 0n);
    const sensitivity = scaled.map((m) => Number(ceil(numerator, m)));
    return (
      BigInt(v.adjustedUnitCostKrw) === ceil(numerator * 12n, sum) &&
      v.baseMonthSensitivityKrwPerM2[0] === Math.min(...sensitivity) &&
      v.baseMonthSensitivityKrwPerM2[1] === Math.max(...sensitivity)
    );
  });
