import { z } from 'zod';
import { cisternDemandDto } from './cisternDemandDto';

export const cisternGameDto = z
  .object({
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
    demandScenario: cisternDemandDto.optional(),
  })
  .refine(
    (v) =>
      !v.demandScenario ||
      (v.roofCollectionAreaM2 === v.demandScenario.roofCollectionAreaM2 &&
        Math.abs(v.capacityM3 - v.demandScenario.capacityM3) < 1e-8),
    { message: '이용조와 수요 비교의 면적·용량 불일치' }
  );
export type CisternGameData = z.infer<typeof cisternGameDto>;
