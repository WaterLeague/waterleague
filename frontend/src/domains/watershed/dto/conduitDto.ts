import { z } from 'zod';
const number = z.number().finite();
const hash = z.string().regex(/^[a-f0-9]{64}$/);
export const conduitGeometryDto = z
  .object({
    shape: z.enum(['CIRCULAR', 'RECT_CLOSED']),
    fullDepthM: number.positive(),
    widthM: number.positive().nullable(),
    barrels: number.int().min(1).max(20),
    roughness: number.positive().max(1),
  })
  .superRefine((v, ctx) => {
    if ((v.shape === 'CIRCULAR') !== (v.widthM === null))
      ctx.addIssue({ code: 'custom', message: '관로 단면의 폭 불일치' });
  });
export const conduitCatalogDto = z.object({
  id: z.literal('SEOUL_PUBLIC_NETWORK_CONDUITS_V1'),
  sourceCatalogSha256: hash,
  sourceOriginalSha256: hash,
  baseNetworkSha256: hash,
  conduits: z
    .array(
      z.object({
        id: z.string(),
        fromNode: z.string(),
        toNode: z.string(),
        lengthM: number.positive(),
        maxFullDepthM: number.positive(),
        inletOffsetM: number,
        outletOffsetM: number,
        original: conduitGeometryDto,
      })
    )
    .min(1),
  designBasis: z.literal('EXPLICIT_DESIGN_NOT_SITE_MEASURED'),
  completeInstalledCostKrw: z.null(),
  limitations: z.array(z.string()),
  sourceUrl: z.url().startsWith('https://'),
});
export type ConduitGeometry = z.infer<typeof conduitGeometryDto>;
export interface ConduitPlacement extends ConduitGeometry {
  id: string;
  conduitId: string;
}
export const conduitDesignDto = z.object({
  catalogHash: hash,
  sourceNetworkSha256: hash,
  placements: z
    .array(
      z.object({
        id: z.string(),
        conduitId: z.string(),
        shape: z.enum(['CIRCULAR', 'RECT_CLOSED']),
        fullDepthM: number.positive(),
        widthM: number.positive().nullable(),
        barrels: number.int().positive(),
        roughness: number.positive(),
        original: conduitGeometryDto,
      })
    )
    .min(1)
    .max(20),
});
