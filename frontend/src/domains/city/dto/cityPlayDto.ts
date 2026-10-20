import { z } from 'zod';
const hash = z.string().regex(/^[a-f0-9]{64}$/);
export const cityPlayDto = z
  .object({
    schemaVersion: z.literal(1),
    id: z.literal('SEOUL_NGII_GAME_V2'),
    rainfallUse: z.literal('ARCHIVED_OBSERVATIONS_ON_CURRENT_PUBLIC_GEOMETRY'),
    siteCatalogSha256: hash,
    regions: z
      .array(
        z.object({
          districtId: z.string().regex(/^11\d{3}$/),
          districtName: z.string(),
          mapId: z.string().regex(/^seoul-ngii-v1-11\d{3}$/),
          defaultModelHash: hash,
          modelHashes: z.array(hash).length(4),
          defaultRainfall: z.object({
            stationId: z.string(),
            stationName: z.string(),
            distanceKm: z.number().nonnegative().max(10),
            use: z.literal('NEAREST_ARCHIVED_QUALITY_CHECKED_AWS_WITHIN_10KM'),
          }),
          center: z.tuple([z.number().finite(), z.number().finite()]),
          roofCount: z.number().int().nonnegative(),
          groundCount: z.number().int().nonnegative(),
          siteCatalogSha256: hash,
          eventModelHashes: z.record(z.string(), hash),
        })
      )
      .length(25),
  })
  .refine(
    (value) =>
      new Set(value.regions.map((row) => row.districtId)).size === 25 &&
      value.regions.every(
        (row) =>
          row.modelHashes.includes(row.defaultModelHash) &&
          row.siteCatalogSha256 === value.siteCatalogSha256
      )
  );
export type CityPlayRegion = z.infer<typeof cityPlayDto>['regions'][number];
