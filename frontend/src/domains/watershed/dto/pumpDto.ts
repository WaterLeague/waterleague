import { z } from 'zod';
const n = z.number().finite();
const hash = z.string().regex(/^[a-f0-9]{64}$/);
export const pumpCatalogDto = z.object({
  id: z.literal('KSB_PA4_500_270_1450_17_V1'),
  model: z.string(),
  classification: z.literal('MANUFACTURER_GRAPH_DIGITIZATION_NOT_SITE_MEASURED'),
  frequencyHz: z.literal(50),
  speedRpm: z.literal(1450),
  bladeAngleDeg: z.literal(17),
  points: z
    .array(
      z.object({
        flowM3h: n.positive(),
        headM: n.positive(),
        shaftPowerKw: n.positive(),
        npshRequiredM: n.positive(),
      })
    )
    .min(2),
  source: z.object({
    author: z.string(),
    document: z.string(),
    page: n.int().positive(),
    sha256: hash,
    url: z.url().startsWith('https://'),
  }),
  extrapolationAllowed: z.literal(false),
  limitations: z.array(z.string()),
});
export interface PumpDelivery {
  lengthM: number;
  diameterM: number;
  roughnessMm: number;
  pressureHeadLimitM: number;
  entranceLoss: number;
  exitLoss: number;
  averageLoss: number;
  checkValve: boolean;
}
export interface PumpPlacement {
  id: string;
  fromNode: string;
  toNode: string;
  startDepthM: number;
  stopDepthM: number;
  initialStatus: 'ON' | 'OFF';
  delivery: PumpDelivery;
}
export const pumpDesignDto = z.object({
  catalogHash: hash,
  sourceNetworkSha256: hash,
  placements: z
    .array(
      z.object({
        id: z.string(),
        fromNode: z.string(),
        toNode: z.string(),
        startDepthM: n.positive(),
        stopDepthM: n.positive(),
        initialStatus: z.enum(['ON', 'OFF']),
        curveId: z.string(),
        delivery: z.object({
          lengthM: n.positive(),
          diameterM: n.positive(),
          roughnessMm: n.positive(),
          pressureHeadLimitM: n.positive(),
          entranceLoss: n.nonnegative(),
          exitLoss: n.nonnegative(),
          averageLoss: n.nonnegative(),
          checkValve: z.boolean(),
        }),
      })
    )
    .min(1)
    .max(20),
});
const status = z.enum(['PASSED', 'FAILED']);
export const pumpOperationDto = z
  .object({
    method: z.literal('NATIVE_ROUTING_STEP_PUMP_OBSERVER_V1'),
    curveStatus: status,
    deliveryStatus: status,
    rankingEligible: z.literal(false),
    pumps: z
      .array(
        z.object({
          linkId: z.string(),
          deliveryNodeId: z.string(),
          transferredM3: n.nonnegative(),
          runningSeconds: n.nonnegative(),
          flowingSeconds: n.nonnegative(),
          startCount: n.int().nonnegative(),
          peakFlowM3s: n.nonnegative(),
          minimumOperatingHeadM: n,
          maximumOperatingHeadM: n,
          outsideHeadCurveSeconds: n.nonnegative(),
          outsideFlowCurveSeconds: n.nonnegative(),
          observedSeconds: n.positive(),
          routingSteps: n.int().positive(),
          shaftEnergyKwh: n.nonnegative().nullable(),
          electricEnergyKwh: z.null(),
          deliveryFloodingM3: n.nonnegative(),
          curveStatus: status,
          deliveryStatus: status,
          cavitationStatus: z.literal('NOT_EVALUATED'),
        })
      )
      .max(20),
  })
  .superRefine((v, ctx) => {
    if (new Set(v.pumps.map((p) => p.linkId)).size !== v.pumps.length)
      ctx.addIssue({ code: 'custom', message: '펌프 운전 기록 중복' });
    for (const p of v.pumps) {
      const valid = p.outsideHeadCurveSeconds === 0 && p.outsideFlowCurveSeconds === 0;
      if (
        (p.curveStatus === 'PASSED') !== valid ||
        (p.shaftEnergyKwh !== null) !== valid ||
        (p.deliveryStatus === 'PASSED') !== p.deliveryFloodingM3 <= 1e-9 ||
        p.runningSeconds > p.observedSeconds + 1e-6 ||
        p.flowingSeconds > p.observedSeconds + 1e-6 ||
        p.minimumOperatingHeadM > p.maximumOperatingHeadM ||
        p.deliveryNodeId !== p.linkId + '_D'
      )
        ctx.addIssue({ code: 'custom', message: '펌프 운전 기록과 판정 불일치' });
    }
    if (
      (v.curveStatus === 'PASSED') !== v.pumps.every((p) => p.curveStatus === 'PASSED') ||
      (v.deliveryStatus === 'PASSED') !== v.pumps.every((p) => p.deliveryStatus === 'PASSED')
    )
      ctx.addIssue({ code: 'custom', message: '펌프 전체 판정 불일치' });
  });
