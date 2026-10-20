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
  inletPipe?: CisternInletPipe | null;
  drainPipe?: CisternInletPipe | null;
  overflowPipe?: CisternInletPipe | null;
}
const number = z.number().finite();
export const cisternInletPipeDto = z.strictObject({
  lengthM: number.min(0.001).max(10000),
  diameterM: number.min(0.001).max(100),
  roughness: number.min(0.001).max(1),
  upstreamInvertM: number.min(-1000).max(10000),
  upstreamMaxDepthM: number.min(0.001).max(100),
  downstreamInvertM: number.min(-1000).max(10000),
});
export type CisternInletPipe = z.infer<typeof cisternInletPipeDto>;
export function validInletElevation(pipe: CisternInletPipe, invert: number, depth: number) {
  const drop = pipe.upstreamInvertM - pipe.downstreamInvertM;
  return (
    pipe.upstreamMaxDepthM >= pipe.diameterM &&
    pipe.downstreamInvertM >= invert &&
    pipe.downstreamInvertM + pipe.diameterM <= invert + depth + 1e-9 &&
    drop >= -1e-9 &&
    drop <= pipe.lengthM + 1e-9
  );
}
export function validOutletElevation(
  pipe: CisternInletPipe,
  port: StoragePort,
  receiver?: { invertM: number; maxDepthM: number }
) {
  const drop = pipe.upstreamInvertM - pipe.downstreamInvertM;
  return (
    pipe.upstreamMaxDepthM >= pipe.diameterM &&
    pipe.upstreamInvertM <= port.crestM + 1e-9 &&
    port.crestM + port.diameterM <= pipe.upstreamInvertM + pipe.upstreamMaxDepthM + 1e-9 &&
    drop >= -1e-9 &&
    drop <= pipe.lengthM + 1e-9 &&
    (!receiver ||
      (pipe.downstreamInvertM >= receiver.invertM &&
        pipe.downstreamInvertM + pipe.diameterM <= receiver.invertM + receiver.maxDepthM + 1e-9))
  );
}
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
    inletPipe: cisternInletPipeDto.optional(),
    drainPipe: cisternInletPipeDto.optional(),
    overflowPipe: cisternInletPipeDto.optional(),
  })
  .superRefine((v, ctx) => {
    const [a, b] = v.depthAreaCurve;
    if (
      a.depthM !== 0 ||
      b.depthM <= 0 ||
      a.areaM2 !== b.areaM2 ||
      a.areaM2 !== v.footprintM2 ||
      v.initialDepthM > b.depthM ||
      (v.inletPipe && !validInletElevation(v.inletPipe, v.invertM, b.depthM)) ||
      (v.drainPipe && ('mode' in v.drain || !validOutletElevation(v.drainPipe, v.drain))) ||
      (v.overflowPipe && !validOutletElevation(v.overflowPipe, v.overflow))
    )
      ctx.addIssue({ code: 'custom', message: '이용조 단면과 저류 용량 불일치' });
  });
