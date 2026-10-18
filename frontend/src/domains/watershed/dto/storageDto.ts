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
      z.object({
        id: z.string(),
        nodeId: z.string(),
        capacityM3: number.positive(),
        initialStorageM3: number,
        inflowM3: number,
        outflowIncludingFloodingM3: number,
        floodingM3: number,
        finalStorageM3: number,
        balanceResidualM3: number,
        allowedResidualM3: number.nonnegative(),
        numericalStatus: z.enum(['PASSED', 'FAILED']),
      })
    ),
  }),
});
