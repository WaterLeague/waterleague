import { z } from 'zod';
const hash = z.string().regex(/^[a-f0-9]{64}$/);
const money = z.number().int().nonnegative().safe();
const source = z.object({
  title: z.string(),
  url: z.url().startsWith('https://'),
  year: z.number().int(),
  sha256: hash,
  pdfPages: z.array(z.number().int().positive()),
});
const classification = z.literal('HISTORICAL_PUBLIC_PLAN_REFERENCE_NOT_CURRENT_QUOTE');
const status = z.enum(['AREA_REFERENCE_ONLY', 'UNPRICED']);
export const watershedCostCatalogDto = z.object({
  schemaVersion: z.literal(1),
  id: z.string(),
  currency: z.literal('KRW'),
  classification,
  source,
  limitations: z.array(z.string()),
  entries: z.record(
    z.string(),
    z.object({
      label: z.string(),
      status,
      unit: z.enum(['M2', 'M']).nullable(),
      unitPriceKrw: money.nullable(),
      sourceQuantity: z.number().finite().positive().nullable(),
      sourceAmountKrw: money.nullable(),
      sourceLabel: z.string().nullable(),
      notes: z.array(z.string()),
    })
  ),
});
export const watershedCostSnapshotDto = z
  .object({
    schemaVersion: z.literal(1),
    catalogHash: hash,
    classification,
    source,
    limitations: z.array(z.string()),
    items: z
      .array(
        z.object({
          placementId: z.string(),
          facilityType: z.string(),
          areaM2: z.number().finite().positive(),
          status,
          referenceAmountKrw: money.nullable(),
          notes: z.array(z.string()),
        })
      )
      .min(1)
      .max(20),
    knownReferenceSubtotalKrw: money.nullable(),
    unpricedPlacementIds: z.array(z.string()),
    completeInstalledCostKrw: z.null(),
    budgetChargedKrw: z.null(),
  })
  .superRefine((v, ctx) => {
    const priced = v.items.filter((i) => i.status === 'AREA_REFERENCE_ONLY');
    const unpriced = v.items.filter((i) => i.status === 'UNPRICED').map((i) => i.placementId);
    if (
      new Set(v.items.map((i) => i.placementId)).size !== v.items.length ||
      v.items.some((i) => (i.status === 'UNPRICED') !== (i.referenceAmountKrw === null)) ||
      JSON.stringify(unpriced) !== JSON.stringify(v.unpricedPlacementIds) ||
      v.knownReferenceSubtotalKrw !==
        (priced.length ? priced.reduce((s, i) => s + (i.referenceAmountKrw ?? 0), 0) : null)
    )
      ctx.addIssue({ code: 'custom', message: '참고 공사비 수량·부분합 불일치' });
  });
export type WatershedCostCatalog = z.infer<typeof watershedCostCatalogDto>;
export type WatershedCostSnapshot = z.infer<typeof watershedCostSnapshotDto>;
