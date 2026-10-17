import { z } from 'zod';
const value = z.number().finite();
export const initializationDto = z.object({
  method: z.string(),
  warmupMinutes: z.number().int().nonnegative(),
  initialSoilMoisture: value.nullable(),
  initialStorageM3: value,
  warmupRainMm: value,
  scoreExcludesWarmup: z.boolean(),
  evaluationStart: z.string().datetime({ offset: true }).optional(),
  aggregateDerivedMinutes: z.number().int().nonnegative().optional(),
  rainfallSourceHashes: z.array(z.string()).optional(),
  evaporationSourceHashes: z.array(z.string()).optional(),
  seed: z.string().optional(),
  limitations: z.array(z.string()).optional(),
});
