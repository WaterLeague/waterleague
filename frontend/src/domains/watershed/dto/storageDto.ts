import { z } from 'zod';
const number = z.number().finite();
const hash = z.string().regex(/^[a-f0-9]{64}$/);
const node = z.object({ id: z.string(), invertM: number, maxDepthM: number.positive() });
export const storageCatalogDto = z.object({
  id: z.literal('SEOUL_PUBLIC_NETWORK_STORAGE_CONNECTIONS_V1'),
  sourceCatalogSha256: hash,
  sourceOriginalSha256: hash,
  baseNetworkSha256: hash,
  sourceUrl: z.url().startsWith('https://'),
  connections: z
    .array(z.object({ id: z.string(), inlet: node, receiver: node, lengthM: number.positive() }))
    .min(1),
  designBasis: z.literal('EXPLICIT_DESIGN_NOT_SITE_MEASURED'),
  facilityType: z.literal('UNDERGROUND_STORAGE'),
  completeInstalledCostKrw: z.null(),
  limitations: z.array(z.string()),
});
export type StorageCatalog = z.infer<typeof storageCatalogDto>;
export interface StoragePort {
  crestM: number;
  diameterM: number;
  dischargeCoefficient: number;
  flapGate: boolean;
}
export interface StoragePlacement {
  id: string;
  connectionId: string;
  areaM2: number;
  invertM: number;
  depthM: number;
  initialDepthM: number;
  inlet: StoragePort;
  drain: StoragePort;
  overflow: StoragePort;
}
const storedPort = z.object({
  nodeId: z.string(),
  crestM: number,
  diameterM: number.positive(),
  dischargeCoefficient: number.positive().max(1),
  flapGate: z.boolean(),
});
export const storageDesignDto = z.object({
  catalogHash: hash,
  sourceNetworkSha256: hash,
  placements: z
    .array(
      z.object({
        id: z.string(),
        facilityType: z.literal('UNDERGROUND_STORAGE'),
        invertM: number,
        initialDepthM: number.nonnegative(),
        depthAreaCurve: z
          .array(z.object({ depthM: number.nonnegative(), areaM2: number.positive() }))
          .length(2),
        inlet: storedPort,
        drain: storedPort,
        overflow: storedPort,
      })
    )
    .min(1)
    .max(20),
});
export const storageSummaryDto = z.object({
  numericalStatus: z.enum(['PASSED', 'FAILED']),
  routingBalanceAlreadyIncludesStorageAndFlows: z.literal(true),
  rankingEligible: z.literal(false),
  wholeRunLedger: z.object({
    numericalStatus: z.enum(['PASSED', 'FAILED']),
    facilities: z.array(
      z
        .object({
          id: z.string(),
          nodeId: z.string(),
          capacityM3: number.positive(),
          nativeCapacityM3: number.positive().optional(),
          volumeBasis: z.literal('EPA_CMS_STORAGE_VOLUME_TO_EXACT_SI_V1').optional(),
          initialAvailableM3: number.optional(),
          finalAvailableM3: number.optional(),
          reuseM3: z.null().optional(),
          reuseStatus: z.literal('NOT_CALCULATED_NO_USE_DEMAND').optional(),
          initialStorageM3: number,
          inflowM3: number,
          outflowIncludingFloodingM3: number,
          floodingM3: number,
          finalStorageM3: number,
          balanceResidualM3: number,
          allowedResidualM3: number.nonnegative(),
          numericalStatus: z.enum(['PASSED', 'FAILED']),
        })
        .superRefine((v, ctx) => {
          const present = [
            v.nativeCapacityM3,
            v.volumeBasis,
            v.initialAvailableM3,
            v.finalAvailableM3,
          ].filter((x) => x !== undefined).length;
          if (
            present > 0 &&
            (present !== 4 ||
              Math.abs(v.nativeCapacityM3! - (v.capacityM3 * 0.028316846592) / 0.02832) >
                Math.max(1e-9, v.capacityM3 * 1e-12) ||
              Math.abs(v.initialAvailableM3! - (v.nativeCapacityM3! - v.initialStorageM3)) > 1e-8 ||
              Math.abs(v.finalAvailableM3! - (v.nativeCapacityM3! - v.finalStorageM3)) > 1e-8 ||
              (v.numericalStatus === 'PASSED' &&
                Math.min(v.initialAvailableM3!, v.finalAvailableM3!) < -1e-8))
          )
            ctx.addIssue({ code: 'custom', message: '계산 용량과 잔여 저장 공간 불일치' });
          if (
            (v.reuseStatus !== undefined || v.reuseM3 !== undefined) &&
            (v.reuseStatus !== 'NOT_CALCULATED_NO_USE_DEMAND' || v.reuseM3 !== null)
          )
            ctx.addIssue({ code: 'custom', message: '사용 수요 없는 재이용량 미산정 상태 불일치' });
        })
    ),
  }),
});
