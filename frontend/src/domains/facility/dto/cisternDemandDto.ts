import { z } from 'zod';

const nonnegative = z.number().finite().nonnegative();
const sha256 = z.string().regex(/^[a-f0-9]{64}$/);
export const cisternDemandDto = z
  .object({
    schemaVersion: z.literal(1),
    status: z.literal('SUCCEEDED'),
    scenarioId: z.literal('JKSWE_2018_AREA_EQUIVALENT_UNIFORM_DEMAND_V1'),
    catalogSha256: sha256,
    inputSha256: sha256,
    classification: z.literal('LITERATURE_BASED_DEMAND_ASSUMPTION'),
    rankingEligible: z.literal(false),
    observedReuseM3: z.null(),
    source: z.object({
      title: z.string().min(1),
      url: z.literal('https://journal.cricit.kr/jkswe/XmlViewer/f253405'),
      doi: z.literal('10.15681/KSWE.2017.34.1.57'),
      publicationYear: z.literal(2018),
      sha256,
      reference: z.string().min(1),
    }),
    newerReview: z.object({
      title: z.string().min(1),
      url: z.literal('https://www.mdpi.com/2073-4441/16/1/96'),
      doi: z.literal('10.3390/w16010096'),
      publicationYear: z.literal(2024),
      reference: z.string().min(1),
      application: z.string().min(1),
    }),
    roofCollectionAreaM2: nonnegative.positive(),
    capacityM3: nonnegative.positive(),
    evaluationStart: z.iso.datetime({ offset: true }),
    evaluationEnd: z.iso.datetime({ offset: true }),
    evaluationSeconds: nonnegative.positive(),
    demandRateM3Day: nonnegative.positive(),
    demandM3: nonnegative.positive(),
    suppliedM3: nonnegative,
    unmetDemandM3: nonnegative,
    supplyFraction: nonnegative.max(1),
    initialStorageM3: nonnegative,
    finalStorageM3: nonnegative,
    inflowM3: nonnegative,
    overflowM3: nonnegative,
    evaporationM3: nonnegative,
    infiltrationM3: nonnegative,
    balanceResidualM3: z.number().finite(),
    runoffContinuityPercent: z.number().finite().min(-1).max(1),
    drain: z.object({
      drainCoefficient: nonnegative.positive(),
      drainExponent: z.literal(0),
      drainOffsetMm: z.literal(0),
      drainDelayHours: z.literal(0),
    }),
    boundary: z.literal('TANK_WITHDRAWAL_NO_DOWNSTREAM_USE_OR_RETURN_FLOW'),
    limitations: z.array(z.string()).min(1),
  })
  .superRefine((v, ctx) => {
    const close = (a: number, b: number) => Math.abs(a - b) <= Math.max(1e-10, Math.abs(b) * 1e-9);
    const residual =
      v.initialStorageM3 +
      v.inflowM3 -
      v.finalStorageM3 -
      v.suppliedM3 -
      v.overflowM3 -
      v.evaporationM3 -
      v.infiltrationM3;
    if (
      !close(
        (Date.parse(v.evaluationEnd) - Date.parse(v.evaluationStart)) / 1000,
        v.evaluationSeconds
      ) ||
      !close(v.demandRateM3Day, (0.201 * v.roofCollectionAreaM2) / 235) ||
      !close(v.capacityM3, v.roofCollectionAreaM2 * 0.01) ||
      !close(v.demandM3, (v.demandRateM3Day * v.evaluationSeconds) / 86400) ||
      v.suppliedM3 > v.demandM3 + Math.max(1e-12, v.demandM3 * 1e-9) ||
      !close(v.unmetDemandM3, Math.max(0, v.demandM3 - v.suppliedM3)) ||
      !close(v.supplyFraction, Math.min(1, v.suppliedM3 / v.demandM3)) ||
      !close(v.drain.drainCoefficient, ((v.demandRateM3Day / v.capacityM3) * 1000) / 24) ||
      Math.max(v.initialStorageM3, v.finalStorageM3) > v.capacityM3 + 1e-8 ||
      !close(residual, v.balanceResidualM3) ||
      Math.abs(residual) > Math.max(1e-8, 0.01 * (v.inflowM3 + v.initialStorageM3))
    )
      ctx.addIssue({ code: 'custom', message: '이용조 수요·공급·기간·물수지 불일치' });
  });

export type CisternDemandData = z.infer<typeof cisternDemandDto>;
