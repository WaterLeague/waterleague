import { z } from 'zod';

export const cisternGameDto = z.object({
  schemaVersion: z.literal(1),
  rulesSha256: z.string().regex(/^[a-f0-9]{64}$/),
  roofCollectionAreaM2: z.number().positive(),
  capacityM3: z.number().positive(),
  initialStorageM3: z.number().finite(),
  finalStorageM3: z.number().finite(),
  inflowM3: z.number().finite(),
  drainageM3: z.number().finite(),
  overflowM3: z.number().finite(),
  reuseM3: z.null(),
  reuseStatus: z.literal('DEMAND_NOT_AVAILABLE'),
  tankPosition: z.literal('SCHEMATIC_NOT_CONSTRUCTION_PLACEMENT'),
  limitations: z.array(z.string()),
});
export type CisternGameData = z.infer<typeof cisternGameDto>;
