import { z } from 'zod';
import type { StoragePort } from './storageDto';
export interface CisternPlacement {
  id: string;
  catchmentId: string;
  captureAreaM2: number;
  areaM2: number;
  invertM: number;
  depthM: number;
  initialDepthM: number;
  drain: StoragePort | null;
  drainClosed?: boolean;
  overflow: StoragePort;
}
const number = z.number().finite();
const port = z.strictObject({
  crestM: number,
  diameterM: number.positive(),
  dischargeCoefficient: number.positive().max(1),
  flapGate: z.boolean(),
});
export const cisternDesignDto = z
  .object({
    schemaVersion: z.union([z.literal(1), z.literal(2), z.literal(3)]),
    catalogHash: z.string().regex(/^[a-f0-9]{64}$/),
    sourceNetworkSha256: z.string().regex(/^[a-f0-9]{64}$/),
    id: z.string(),
    subcatchmentId: z.string(),
    captureAreaM2: number.positive(),
    footprintM2: number.positive(),
    invertM: number,
    initialDepthM: number.nonnegative(),
    depthAreaCurve: z
      .array(z.object({ depthM: number.nonnegative(), areaM2: number.positive() }))
      .length(2),
    drain: z.union([port, z.strictObject({ mode: z.literal('CLOSED_NO_WITHDRAWAL') })]),
    overflow: port,
  })
  .superRefine((v, ctx) => {
    const [a, b] = v.depthAreaCurve;
    if (
      a.depthM !== 0 ||
      b.depthM <= 0 ||
      a.areaM2 !== b.areaM2 ||
      a.areaM2 !== v.footprintM2 ||
      v.initialDepthM > b.depthM
    )
      ctx.addIssue({ code: 'custom', message: '이용조 단면과 저류 용량 불일치' });
  });
