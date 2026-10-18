import { z } from 'zod';
const n = z.number().finite();
const at = z.iso.datetime({ offset: true });
const method = z.literal('NATIVE_RUNOFF_STEP_SURFACE_PLUS_DRAIN_V1');
const close = (a: number, b: number) => Math.abs(a - b) <= Math.max(1e-8, Math.abs(a) * 1e-8);
const row = z
  .object({
    id: z.enum(['baseline', 'strategy']),
    dischargeM3: n,
    initialStorageM3: n,
    finalStorageM3: n,
    netStorageM3: n,
    accountedDischargeM3: n,
    precipitationM3: n,
    infiltrationM3: n,
    evaporationM3: n,
    balanceResidualM3: n,
    nativeIntegralDifferenceM3: n,
    metrics: z.object({
      method,
      scope: z.literal('SELECTED_SURFACE_OUTLET_NOT_SEWER_OR_RIVER'),
      start: at,
      end: at,
      stepCount: n.int().positive(),
      maximumStepSeconds: n.positive(),
      observedSeconds: n.positive(),
      dischargeIntegralM3: n,
      peakM3s: n.nonnegative(),
      peakAt: at.nullable(),
      minimumComponentRateM3s: n,
      peakTimeConvention: z.literal('END_OF_NATIVE_RUNOFF_INTERVAL'),
      implementationSha256: z.string().regex(/^[a-f0-9]{64}$/),
    }),
  })
  .refine((v) => {
    const m = v.metrics,
      start = Date.parse(m.start),
      end = Date.parse(m.end);
    return (
      end > start &&
      close((end - start) / 1000, m.observedSeconds) &&
      (m.peakAt === null
        ? m.peakM3s === 0
        : m.peakM3s > 0 && Date.parse(m.peakAt) > start && Date.parse(m.peakAt) <= end) &&
      close(v.netStorageM3, v.finalStorageM3 - v.initialStorageM3) &&
      close(v.accountedDischargeM3, v.dischargeM3 + v.netStorageM3) &&
      close(
        v.balanceResidualM3,
        v.precipitationM3 - v.evaporationM3 - v.infiltrationM3 - v.accountedDischargeM3
      ) &&
      close(v.nativeIntegralDifferenceM3, m.dischargeIntegralM3 - v.dischargeM3)
    );
  });
export const runoffComparisonDto = z
  .object({
    schemaVersion: z.literal(1),
    method,
    cases: z.array(row).length(2),
    dischargeReductionM3: n,
    netStorageIncreaseM3: n,
    accountedReductionM3: n,
    peakReductionM3s: n,
    limitations: z.array(z.string()),
  })
  .refine((v) => {
    const a = v.cases.find((c) => c.id === 'baseline'),
      b = v.cases.find((c) => c.id === 'strategy');
    return (
      !!a &&
      !!b &&
      a.metrics.start === b.metrics.start &&
      a.metrics.end === b.metrics.end &&
      close(v.dischargeReductionM3, a.dischargeM3 - b.dischargeM3) &&
      close(v.netStorageIncreaseM3, b.netStorageM3 - a.netStorageM3) &&
      close(v.accountedReductionM3, a.accountedDischargeM3 - b.accountedDischargeM3) &&
      close(v.peakReductionM3s, a.metrics.peakM3s - b.metrics.peakM3s)
    );
  });
export type RunoffComparisonData = z.infer<typeof runoffComparisonDto>;
