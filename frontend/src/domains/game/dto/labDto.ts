import { z } from 'zod';
const positive = z.number().finite().positive();
const coordinate = z.tuple([z.number().finite(), z.number().finite()]);
const rainfallUse = z.enum([
  'COMMON_OBSERVED_REPLAY_NOT_LOCAL_OBSERVATION',
  'NEAREST_AWS_OBSERVED_REPLAY',
  'OBSERVED_REPLAY',
]);
const facility = z.enum(['RAIN_GARDEN', 'PERMEABLE_PAVEMENT', 'GREEN_ROOF']);
export const labDto = z.object({
  modelHash: z.string().regex(/^[a-f0-9]{64}$/),
  model: z.object({
    id: z.string(),
    title: z.string(),
    mapId: z.string().optional(),
    mapTitle: z.string().optional(),
    regionalRainfallUse: rainfallUse.optional(),
    validationLevel: z.literal('EXPLORATORY'),
    officialEvaluationAvailable: z.literal(false),
    simulationAvailable: z.boolean(),
    engine: z.string(),
    currency: z.literal('KRW'),
    budget: positive,
    maxPlacements: z.number().int().positive(),
    unitCosts: z.record(facility, positive),
    costModel: z.object({
      source: z.object({ url: z.url({ protocol: /^https$/ }) }).nullish(),
      currency: z.literal('KRW'),
      evidence: z.string(),
      note: z.string(),
      exclusions: z.array(z.string()),
    }),
    cells: z
      .array(
        z.object({
          id: z.string(),
          name: z.string(),
          buildingId: z.string().optional(),
          kind: z.enum(['ROOF', 'GROUND']),
          coordinates: z.array(coordinate).min(4),
          center: coordinate,
          heightM: z.number().finite().nonnegative(),
          areaM2: positive,
          maxAreaM2: positive,
          allowedTypes: z.array(facility).min(1),
          areaEvidence: z.string(),
          eligibilityEvidence: z.string(),
        })
      )
      .min(1),
    rainfall: z.object({
      start: z.iso.datetime({ offset: true }),
      end: z.iso.datetime({ offset: true }),
      intervalSeconds: z.literal(60),
      depthsMm: z.array(z.number().finite().nonnegative()).min(2).max(10080),
      totalDepthMm: positive,
      provider: z.string(),
      stationName: z.string(),
      stationId: z.string(),
      quality: z.string(),
      sourceHash: z.string().regex(/^[a-f0-9]{64}$/),
      sourceUrl: z.url({ protocol: /^https$/ }),
      checks: z.array(z.string()),
      limitations: z.array(z.string()),
      attribution: z.string(),
      stationDistanceKm: z.number().finite().nonnegative().optional(),
      stationDistanceEvidence: z.string().optional(),
      windowStatistics: z
        .object({
          peak15MinuteMm: z.number().finite().nonnegative(),
          peak60MinuteMm: z.number().finite().nonnegative(),
          observedDryLeadMinutes: z.number().int().nonnegative(),
          observedDryTailMinutes: z.number().int().nonnegative(),
        })
        .optional(),
    }),
    assumptions: z.array(z.string()),
    scoreRule: z.literal('VOLUME_WITH_FINAL_STORAGE_V1'),
  }),
});
export type LabDto = z.infer<typeof labDto>;

export const rainfallCatalogDto = z.object({
  defaultModelHash: z.string().regex(/^[a-f0-9]{64}$/),
  models: z
    .array(
      z.object({
        modelHash: z.string().regex(/^[a-f0-9]{64}$/),
        title: z.string(),
        mapId: z.string().optional(),
        mapTitle: z.string().optional(),
        regionalRainfallUse: rainfallUse.optional(),
        budget: positive,
        validationLevel: z.literal('EXPLORATORY'),
        official: z.literal(false),
        rainfall: labDto.shape.model.shape.rainfall.omit({ depthsMm: true }),
      })
    )
    .min(1)
    .max(256),
});
