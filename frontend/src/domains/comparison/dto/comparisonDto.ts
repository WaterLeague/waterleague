import { z } from 'zod';
const hash = z.string().regex(/^[a-f0-9]{64}$/),
  time = z.iso.datetime({ offset: true });
const placement = z.object({
  cellId: z.string().min(1).max(30),
  facilityType: z.enum([
    'RAIN_GARDEN',
    'PERMEABLE_PAVEMENT',
    'GREEN_ROOF',
    'BIORETENTION',
    'VEGETATIVE_SWALE',
    'INFILTRATION_TRENCH',
  ]),
  areaM2: z.number().positive(),
});
const metrics = z.object({
  runoffM3: z.number().nonnegative(),
  surfaceRunoffM3: z.number().nonnegative(),
  lidDrainageM3: z.number().nonnegative(),
  finalStorageM3: z.number().nonnegative(),
  initialStorageM3: z.number().nonnegative(),
  accountedDischargeM3: z.number().nonnegative(),
  infiltrationM3: z.number().nonnegative(),
  evaporationM3: z.number().nonnegative(),
  precipitationM3: z.number().nonnegative(),
  runoffContinuityPercent: z.number().min(-1).max(1),
  peakM3s: z.number().nonnegative(),
  seriesM3s: z.array(z.number().nonnegative()).max(10080),
});
const result = z.object({
  score: z.number().max(100),
  official: z.literal(false),
  validationLevel: z.literal('EXPLORATORY'),
  baseline: metrics,
  strategy: metrics,
  assumptions: z.array(z.string()),
  sensitivity: z.array(
    z.object({
      conductivityFactor: z.number().positive(),
      score: z.number(),
      runoffM3: z.number().nonnegative(),
    })
  ),
  engine: z.object({
    version: z.string(),
    binarySha256: hash,
    generatorSha256: hash,
    platform: z.string(),
  }),
});
export const summaryDto = z.object({
  id: z.uuid(),
  title: z.string().max(80),
  sourceVersionId: z.uuid(),
  createdAt: time,
});
export const comparisonDto = summaryDto.extend({
  sourceVersion: z.object({
    id: z.uuid(),
    strategyId: z.uuid(),
    revision: z.number().int().positive(),
    modelHash: hash,
    inputHash: hash,
    placements: z.array(placement).max(50),
    designNote: z.string().max(2000),
    cost: z.number().nonnegative().max(300000000),
    currency: z.literal('KRW'),
    createdAt: time,
    events: z.object({ kind: z.string(), before: z.array(placement), after: z.array(placement) }),
  }),
  jobs: z
    .array(
      z.object({
        id: z.uuid(),
        versionId: z.uuid(),
        strategyId: z.uuid(),
        state: z.enum(['QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED', 'REJECTED']),
        result: result.nullable(),
        errorCode: z.string().nullable(),
        createdAt: time,
        modelHash: hash,
        inputHash: hash,
      })
    )
    .min(2)
    .max(3),
});
