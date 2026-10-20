import { z } from 'zod';
import { initializationDto } from './initializationDto';
import { sensitivityMetricsDto } from './sensitivityMetricsDto';
import { cisternDemandDto } from '../../facility/dto/cisternDemandDto';

const finite = z.number().finite();
const amount = finite.nonnegative();
const sha256 = z.string().regex(/^[a-f0-9]{64}$/);
const time = z.iso.datetime({ offset: true });
const operation = z.enum(['NATURAL_DRAIN', 'LITERATURE_DEMAND']);
const condition = {
  days: z.literal(7),
  seedSaturationPercent: z.union([z.literal(0), z.literal(100)]),
  operation,
};
const tank = z.object({
  initialStorageM3: amount,
  finalStorageM3: amount,
  inflowM3: amount,
  outflowM3: amount,
  overflowM3: amount,
  evaporationM3: amount,
  infiltrationM3: amount,
  balanceResidualM3: finite,
});
const caseDto = z.discriminatedUnion('status', [
  z.object({
    ...condition,
    status: z.literal('SUCCEEDED'),
    inputSha256: sha256,
    nativeSeedStorageM3: amount,
    preparationStart: time,
    metrics: sensitivityMetricsDto,
    tank,
    initialization: initializationDto,
    demand: cisternDemandDto.nullable(),
    runoffContinuityPercent: finite.min(-1).max(1),
    evaluationBalanceResidualM3: finite,
  }),
  z.object({ ...condition, status: z.literal('FAILED'), errorCode: z.string() }),
]);
const comparison = z.discriminatedUnion('status', [
  z.object({ status: z.literal('INCOMPLETE'), seedDifferences: z.null(), ranges: z.null() }),
  z.object({
    status: z.literal('MEASURED_NO_UNIVERSAL_CONVERGENCE_THRESHOLD'),
    seedDifferences: z
      .array(z.object({ days: z.literal(7), wetMinusDry: sensitivityMetricsDto }))
      .length(1),
  }),
]);

export const cisternInitializationDto = z
  .object({
    schemaVersion: z.literal(3),
    method: z.literal('OBSERVED_CISTERN_STORAGE_DEMAND_COMPARISON_V3'),
    scope: z.literal('INPUT_BOUND_INDEPENDENT_SURFACE_ONLY'),
    seedPolicy: z.literal('CISTERN_EMPTY_FULL_STORAGE_BOUNDARIES'),
    rankingEligible: z.literal(false),
    inputSha256: sha256,
    cellId: z.string().min(1),
    facilityType: z.literal('RAINWATER_CISTERN'),
    areaM2: amount.positive(),
    capacityM3: amount.positive(),
    evaluationStart: time,
    evaluationEnd: time,
    rulesSha256: sha256,
    demandCatalogSha256: sha256,
    status: z.enum(['SUCCEEDED', 'INCOMPLETE']),
    cases: z.array(caseDto).length(4),
    comparisons: z.array(z.object({ operation, comparison })).length(2),
    seedEvidence: z.object({
      method: z.literal('EPA_SWMM_5_2_4_LID_INIT_STATE'),
      url: z.literal(
        'https://raw.githubusercontent.com/USEPA/Stormwater-Management-Model/v5.2.4/src/solver/lid.c'
      ),
      reference: z.string().min(1),
    }),
    limitations: z.array(z.string()).min(1),
  })
  .superRefine((v, ctx) => {
    const reject = () =>
      ctx.addIssue({ code: 'custom', message: '이용조 초기 저류·운전·평가 근거 불일치' });
    const close = (a: number | null, b: number | null): boolean =>
      a === null || b === null ? a === b : Math.abs(a - b) <= Math.max(1e-8, Math.abs(b) * 1e-9);
    const start = Date.parse(v.evaluationStart),
      end = Date.parse(v.evaluationEnd);
    if (
      start >= end ||
      !close(v.capacityM3, v.areaM2 * 0.01) ||
      new Set(v.cases.map((c) => `${c.operation}:${c.seedSaturationPercent}`)).size !== 4 ||
      new Set(v.comparisons.map((c) => c.operation)).size !== 2 ||
      (v.status === 'SUCCEEDED') !== v.cases.every((c) => c.status === 'SUCCEEDED')
    )
      reject();
    for (const c of v.cases) {
      if (c.status !== 'SUCCEEDED') continue;
      const t = c.tank,
        d = c.demand;
      const residual =
        t.initialStorageM3 +
        t.inflowM3 -
        t.finalStorageM3 -
        t.outflowM3 -
        t.overflowM3 -
        t.evaporationM3 -
        t.infiltrationM3;
      if (
        !close(c.nativeSeedStorageM3, (v.capacityM3 * c.seedSaturationPercent) / 100) ||
        Date.parse(c.preparationStart) !== start - 7 * 86400000 ||
        Date.parse(c.initialization.evaluationStart ?? '') !== start ||
        c.initialization.warmupMinutes !== 10080 ||
        !c.initialization.scoreExcludesWarmup ||
        c.initialization.seed !==
          (c.seedSaturationPercent === 0 ? 'EMPTY_CISTERN' : 'FULL_CISTERN') ||
        Math.max(t.initialStorageM3, t.finalStorageM3) > v.capacityM3 + 1e-8 ||
        !close(t.initialStorageM3, c.metrics.initialLidStorageM3) ||
        !close(residual, t.balanceResidualM3) ||
        Math.abs(residual) > Math.max(1e-8, 0.01 * (t.initialStorageM3 + t.inflowM3)) ||
        (c.operation === 'LITERATURE_DEMAND') !== (d !== null)
      )
        reject();
      if (
        d &&
        (d.catalogSha256 !== v.demandCatalogSha256 ||
          d.inputSha256 !== c.inputSha256 ||
          Date.parse(d.evaluationStart) !== start ||
          Date.parse(d.evaluationEnd) !== end ||
          !close(d.roofCollectionAreaM2, v.areaM2) ||
          !close(d.capacityM3, v.capacityM3) ||
          !close(d.suppliedM3, t.outflowM3) ||
          !close(d.inflowM3, t.inflowM3) ||
          !close(d.overflowM3, t.overflowM3) ||
          !close(d.initialStorageM3, t.initialStorageM3) ||
          !close(d.finalStorageM3, t.finalStorageM3))
      )
        reject();
    }
    for (const item of v.comparisons) {
      const rows = v.cases
        .filter((c) => c.operation === item.operation)
        .sort((a, b) => a.seedSaturationPercent - b.seedSaturationPercent);
      if ((item.comparison.status === 'INCOMPLETE') !== rows.some((c) => c.status === 'FAILED'))
        reject();
      if (
        item.comparison.status !== 'INCOMPLETE' &&
        rows.length === 2 &&
        rows[0].status === 'SUCCEEDED' &&
        rows[1].status === 'SUCCEEDED'
      ) {
        const difference = item.comparison.seedDifferences[0].wetMinusDry;
        for (const key of Object.keys(difference) as (keyof typeof difference)[]) {
          const a = rows[0].metrics[key],
            b = rows[1].metrics[key];
          if (!close(difference[key], a === null || b === null ? null : b - a)) reject();
        }
      }
    }
  });

export type CisternInitializationData = z.infer<typeof cisternInitializationDto>;
