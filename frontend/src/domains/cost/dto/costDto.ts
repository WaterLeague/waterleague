import { z } from 'zod';

const hash = z.string().regex(/^[a-f0-9]{64}$/);
const amount = z.number().finite().nonnegative();
export const costSourceDto = z.object({
  unitCost: z.number().positive(),
  sourceTitle: z.string(),
  sourceUrl: z.url().startsWith('https://'),
  sourceSha256: hash,
  referenceYear: z.number().int(),
  evidence: z.string(),
  scope: z.string(),
  includes: z.array(z.string()),
  excludes: z.array(z.string()),
  note: z.string(),
});
export const costEstimateDto = z
  .object({
    version: z.literal('PUBLIC_REFERENCE_QUANTITY_V1'),
    currency: z.literal('KRW'),
    districtId: z.string(),
    cellId: z.string(),
    siteModelHash: hash,
    facilityType: z.enum([
      'RAIN_GARDEN',
      'PERMEABLE_PAVEMENT',
      'GREEN_ROOF',
      'BIORETENTION',
      'VEGETATIVE_SWALE',
    ]),
    quantityM2: z.number().positive(),
    unitCostKrw: z.number().positive(),
    referenceSubtotalKrw: amount,
    budgetChargeKrw: amount,
    completeInstalledCostKrw: z.null(),
    priceBaseYear: z.null(),
    vat: z.literal('UNCONFIRMED'),
    priceAdjustment: z.literal('NONE'),
    currentPriceVerified: z.literal(false),
    historicalPriceEligible: z.literal(false),
    costSourceSha256: hash,
    source: costSourceDto,
    lines: z
      .array(
        z.object({
          id: z.literal('REFERENCE_INSTALLATION'),
          label: z.string(),
          quantity: z.number().positive(),
          quantityUnit: z.literal('M2'),
          unitCostKrw: z.number().positive(),
          amountKrw: amount,
        })
      )
      .length(1),
    unpricedItems: z.array(
      z.object({ label: z.string(), amountKrw: z.null(), status: z.literal('UNPRICED') })
    ),
  })
  .refine(
    (v) =>
      v.unitCostKrw === v.source.unitCost &&
      v.referenceSubtotalKrw === v.budgetChargeKrw &&
      Math.abs(v.quantityM2 * v.unitCostKrw - v.referenceSubtotalKrw) < 0.005 &&
      v.lines[0].quantity === v.quantityM2 &&
      v.lines[0].unitCostKrw === v.unitCostKrw &&
      v.lines[0].amountKrw === v.referenceSubtotalKrw
  );
export const costRecordDto = z.discriminatedUnion('status', [
  z.object({ status: z.literal('RECORDED'), sha256: hash, estimate: costEstimateDto }),
  z.object({ status: z.literal('NOT_RECORDED'), sha256: z.null(), estimate: z.null() }),
]);
export type CostSource = z.infer<typeof costSourceDto>;
export type CostRecord = z.infer<typeof costRecordDto>;
