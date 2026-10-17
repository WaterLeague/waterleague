import { z } from 'zod';

const coordinate = z.number().finite().min(-60000).max(60000);
export const infrastructureAssetDto = z.object({
  id: z.string().min(1).max(100),
  sourceId: z.string(),
  name: z.string().max(180),
  kind: z.enum([
    'STORM_PUMP',
    'RAINWATER_FACILITY',
    'INFILTRATION_OTHER',
    'INFILTRATION_GUTTER',
    'INFILTRATION_PIT',
    'INFILTRATION_TRENCH',
    'RAINWATER_REUSE',
  ]),
  center: z.tuple([coordinate, coordinate]),
  districtId: z.string(),
  geometryEvidence: z.literal('LOCATION_POINT'),
  verticalLayer: z.literal('UNKNOWN'),
  validFrom: z.null(),
  validTo: z.null(),
  operationStatus: z.literal('UNKNOWN'),
  hydraulicStatus: z.literal('UNCONNECTED'),
  pumpSpecs: z
    .object({
      asOf: z.iso.date(),
      address: z.string(),
      basinAreaHa: z.number().positive(),
      storageCapacityM3: z.number().positive(),
      units: z
        .array(
          z.object({
            unit: z.number().int().positive(),
            powerHp: z.number().positive(),
            capacityM3Min: z.number().positive(),
          })
        )
        .max(100),
    })
    .nullable(),
});
export const infrastructureSourceDto = z.object({
  id: z.string(),
  title: z.string(),
  publisher: z.string(),
  url: z.url().refine((v) => ['data.seoul.go.kr', 'www.data.go.kr'].includes(new URL(v).hostname)),
  sha256: z.string().regex(/^[a-f0-9]{64}$/),
  license: z.literal('KOGL_TYPE_1'),
  fileModifiedAt: z.iso.date().nullable(),
  portalUpdatedAt: z.iso.date().nullable(),
  referenceDate: z.iso.date().nullable(),
  retrievedAt: z.string(),
  crs: z.string(),
  records: z.number().int(),
});
export const infrastructureDto = z
  .object({
    version: z.literal('seoul-public-20261018-v1'),
    sha256: z.string().regex(/^[a-f0-9]{64}$/),
    usage: z.literal('REFERENCE_ONLY'),
    statusCounts: z.record(z.string(), z.number().int().nonnegative()),
    sources: z.array(infrastructureSourceDto).max(50),
    assets: z.array(infrastructureAssetDto).max(5000),
  })
  .refine((v) => {
    const sources = new Set(v.sources.map((s) => s.id));
    return (
      v.assets.every((a) => sources.has(a.sourceId)) &&
      new Set(v.assets.map((a) => a.id)).size === v.assets.length
    );
  });
