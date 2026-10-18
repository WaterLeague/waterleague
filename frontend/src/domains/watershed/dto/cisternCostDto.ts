import { z } from 'zod';
const money = z.number().int().nonnegative().safe();
const hash = z.string().regex(/^[a-f0-9]{64}$/);
const components = z.object({
  BARREL: money.nullable(),
  PIPE: money.nullable(),
  PUMP: money.nullable(),
  LOG: money.nullable(),
  ETC: money.nullable(),
});
const source = z.object({
  title: z.string(),
  url: z.url().startsWith('https://'),
  publicationYear: z.number().int(),
  priceYear: z.null(),
  quoteDate: z.null(),
  sha256: hash,
  reference: z.string(),
  licence: z.string(),
  licenceUrl: z.url(),
});
export const cisternCostCatalogDto = z.object({
  id: z.literal('JKSWE_CISTERN_QUOTES_2018_V1'),
  unitCapacityM3: z.literal('2.35'),
  source,
  limitations: z.array(z.string()),
  quotes: z
    .array(
      z.object({ id: z.enum(['A', 'B', 'C']), totalKrw: money, materialsKrw: money, components })
    )
    .length(3),
  annualOperation: z.object({
    ratesOnInitialCost: z.array(z.object({ id: z.string(), rate: z.string() })),
    cleaning: z.object({ costKrw: money, households: z.number().int().positive() }),
  }),
});
const quote = z.object({
  id: z.enum(['A', 'B', 'C']),
  quotedSubtotalKrw: money,
  materialsKrw: money,
  components,
  unclassifiedDifferenceKrw: money,
  annualComponentsKrw: z.object({
    ELECTRICITY: money,
    MONITORING: money,
    REPAIR_LABOUR_ETC: money,
    CLEANING: money,
  }),
  annualEstimateKrw: money,
});
export const cisternCostSnapshotDto = z
  .object({
    schemaVersion: z.literal(1),
    catalogHash: hash,
    method: z.literal('CAPACITY_EQUIVALENT_QUOTES_NOT_ASSEMBLY_MATCH_V1'),
    unitCapacityM3: z.literal(2.35),
    source,
    limitations: z.array(z.string()),
    completeInstalledCostKrw: z.null(),
    budgetChargedKrw: z.null(),
    items: z
      .array(
        z.object({
          placementId: z.string(),
          capacityM3: z.number().finite().positive(),
          equivalentUnits: z.number().int().min(1).max(256).nullable(),
          status: z.enum(['CAPACITY_NOT_MATCHED', 'CAPACITY_EQUIVALENT_ONLY']),
          quotes: z.array(quote),
        })
      )
      .min(1)
      .max(20),
  })
  .superRefine((v, ctx) => {
    if (
      new Set(v.items.map((i) => i.placementId)).size !== v.items.length ||
      v.items.some(
        (i) =>
          (i.status === 'CAPACITY_NOT_MATCHED'
            ? i.equivalentUnits !== null || i.quotes.length !== 0
            : i.equivalentUnits === null ||
              Math.abs(i.capacityM3 - i.equivalentUnits * 2.35) > 1e-9 ||
              i.quotes.length !== 3 ||
              new Set(i.quotes.map((q) => q.id)).size !== 3) ||
          i.quotes.some(
            (q) =>
              Object.values(q.components).reduce<number>((s, x) => s + (x ?? 0), 0) !==
                q.materialsKrw ||
              q.materialsKrw + q.unclassifiedDifferenceKrw !== q.quotedSubtotalKrw ||
              Object.values(q.annualComponentsKrw).reduce((s, x) => s + x, 0) !==
                q.annualEstimateKrw
          )
      )
    )
      ctx.addIssue({ code: 'custom', message: '이용조 용량·견적 소계 불일치' });
  });
export type CisternCostCatalog = z.infer<typeof cisternCostCatalogDto>;
export type CisternCostSnapshot = z.infer<typeof cisternCostSnapshotDto>;
