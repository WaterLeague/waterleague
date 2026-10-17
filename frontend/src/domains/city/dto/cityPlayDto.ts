import { z } from 'zod';
const hash = z.string().regex(/^[a-f0-9]{64}$/);
export const cityPlayDto = z
  .object({
    schemaVersion: z.literal(1),
    rainfallUse: z.enum([
      'COMMON_OBSERVED_REPLAY_NOT_LOCAL_OBSERVATION',
      'COMMON_AND_NEAREST_AWS_OBSERVED_REPLAY',
    ]),
    regions: z
      .array(
        z.object({
          districtId: z.string().regex(/^\d+$/),
          districtName: z.string(),
          mapId: z.string().regex(/^seoul-osm-v1-\d+$/),
          defaultModelHash: hash,
          modelHashes: z.array(hash).min(3).max(6),
          defaultRainfall: z
            .object({
              stationId: z.string(),
              stationName: z.string(),
              distanceKm: z.number().finite().nonnegative().max(10),
              use: z.literal('NEAREST_AWS_OBSERVED_REPLAY'),
            })
            .optional(),
          center: z.tuple([z.number().finite(), z.number().finite()]),
          roofCount: z.literal(8),
          groundCount: z.literal(5),
        })
      )
      .length(25),
  })
  .refine(
    (r) =>
      new Set(r.regions.map((x) => x.districtId)).size === 25 &&
      r.regions.every((x) => x.modelHashes.includes(x.defaultModelHash))
  );
export type CityPlayRegion = z.infer<typeof cityPlayDto>['regions'][number];
