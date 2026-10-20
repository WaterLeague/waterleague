import { z } from 'zod';

const coordinate = z.number().finite().min(-60000).max(60000);
const point = z.tuple([coordinate, coordinate]);
export const infrastructureFootprintDto = z
  .object({
    polygons: z.array(z.array(z.array(point).min(4)).min(1)).min(1),
    areaM2: z.number().positive(),
    sourceObjectUrl: z
      .string()
      .regex(/^https:\/\/www\.openstreetmap\.org\/(way|relation)\/[0-9]+$/),
    mappedAt: z.iso.date(),
    basinType: z.enum(['detention', 'retention', 'infiltration']).optional(),
    buildingId: z
      .string()
      .regex(/^[WR][0-9]+$/)
      .optional(),
    displayHeightM: z.number().positive().max(1000).optional(),
    heightBasis: z.literal('EXISTING_CITY_DISPLAY_ASSUMPTION').optional(),
    basis: z.literal('PUBLIC_OSM_MAPPING_NOT_SURVEYED_OR_AS_BUILT'),
    policyVersion: z.enum([
      'seoul-basin-footprints-20261018-v1',
      'seoul-pump-buildings-20261019-v1',
    ]),
  })
  .refine((v) =>
    v.buildingId
      ? v.displayHeightM !== undefined && v.heightBasis !== undefined && !v.basinType
      : !!v.basinType
  );
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
    'RETENTION_BASIN',
  ]),
  center: z.tuple([coordinate, coordinate]),
  districtId: z.string(),
  geometryEvidence: z.enum(['LOCATION_POINT', 'PUBLIC_MAPPED_FOOTPRINT', 'PUBLIC_MAPPED_BUILDING']),
  verticalLayer: z.enum(['UNKNOWN', 'MAPPED_SURFACE', 'MAPPED_BUILDING']),
  validFrom: z.null(),
  validTo: z.null(),
  operationStatus: z.literal('UNKNOWN'),
  hydraulicStatus: z.literal('UNCONNECTED'),
  footprint: infrastructureFootprintDto.nullish(),
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
  url: z
    .url()
    .refine((v) =>
      ['data.seoul.go.kr', 'www.data.go.kr', 'www.openstreetmap.org'].includes(new URL(v).hostname)
    ),
  sha256: z.string().regex(/^[a-f0-9]{64}$/),
  license: z.enum(['KOGL_TYPE_1', 'ODbL-1.0']),
  fileModifiedAt: z.iso.date().nullable(),
  portalUpdatedAt: z.iso.date().nullable(),
  referenceDate: z.iso.date().nullable(),
  retrievedAt: z.string(),
  crs: z.string(),
  records: z.number().int(),
});
export const infrastructureDto = z
  .object({
    version: z.literal('seoul-native-infrastructure-20261020-v1'),
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
