import { z } from 'zod';
import { metricComparisonDto } from './metricComparisonDto';
const n = z.number().finite();
const at = z.iso.datetime({ offset: true });
const method = z.literal('NATIVE_RUNOFF_STEP_SURFACE_PLUS_DRAIN_V1');
const timingMethod = z.literal('NATIVE_RUNOFF_VOLUME_CENTROID_V1');
const close = (a: number, b: number) => Math.abs(a - b) <= Math.max(1e-8, Math.abs(a) * 1e-8);
const timing = z.object({
  method: timingMethod,
  firstMomentM3Seconds: n,
  centroidSeconds: n.nonnegative().nullable(),
  status: z.enum(['COMPUTED', 'UNAVAILABLE', 'WITHHELD']),
  reason: z.enum(['NO_DISCHARGE', 'NEGATIVE_COMPONENT_RATE']).nullable(),
});
const detention = z.object({
  schemaVersion: z.literal(1),
  method: timingMethod,
  status: z.enum(['COMPARABLE', 'UNAVAILABLE', 'WITHHELD']),
  reason: z
    .enum([
      'BASELINE_NO_DISCHARGE',
      'STRATEGY_NO_DISCHARGE',
      'BASELINE_NEGATIVE_COMPONENT_RATE',
      'STRATEGY_NEGATIVE_COMPONENT_RATE',
    ])
    .nullable(),
  centroidDelaySeconds: n.nullable(),
  evaluationWindowOnly: z.literal(true),
  rankingEligible: z.literal(false),
});
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
      timing: timing.optional(),
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
      close(v.nativeIntegralDifferenceM3, m.dischargeIntegralM3 - v.dischargeM3) &&
      (!m.timing ||
        (m.minimumComponentRateM3s < 0
          ? m.timing.status === 'WITHHELD' &&
            m.timing.reason === 'NEGATIVE_COMPONENT_RATE' &&
            m.timing.centroidSeconds === null
          : m.dischargeIntegralM3 === 0
            ? m.timing.status === 'UNAVAILABLE' &&
              m.timing.reason === 'NO_DISCHARGE' &&
              m.timing.centroidSeconds === null &&
              m.timing.firstMomentM3Seconds === 0
            : m.dischargeIntegralM3 > 0 &&
              m.timing.status === 'COMPUTED' &&
              m.timing.reason === null &&
              m.timing.centroidSeconds !== null &&
              m.timing.centroidSeconds <= m.observedSeconds &&
              m.timing.firstMomentM3Seconds >= 0 &&
              close(
                m.timing.centroidSeconds,
                m.timing.firstMomentM3Seconds / m.dischargeIntegralM3
              )))
    );
  });
export const runoffComparisonDto = z
  .object({
    schemaVersion: z.union([z.literal(1), z.literal(2), z.literal(3)]),
    method,
    cases: z.array(row).length(2),
    dischargeReductionM3: n,
    netStorageIncreaseM3: n,
    accountedReductionM3: n,
    peakReductionM3s: n,
    limitations: z.array(z.string()),
    metricComparison: metricComparisonDto.optional(),
    detention: detention.optional(),
  })
  .refine((v) => {
    const a = v.cases.find((c) => c.id === 'baseline'),
      b = v.cases.find((c) => c.id === 'strategy');
    return (
      !!a &&
      !!b &&
      (v.schemaVersion === 1 || v.metricComparison !== undefined) &&
      (v.schemaVersion !== 3 || (!!v.detention && !!a.metrics.timing && !!b.metrics.timing)) &&
      (v.schemaVersion === 3 || (!v.detention && !a.metrics.timing && !b.metrics.timing)) &&
      a.metrics.start === b.metrics.start &&
      a.metrics.end === b.metrics.end &&
      close(v.dischargeReductionM3, a.dischargeM3 - b.dischargeM3) &&
      close(v.netStorageIncreaseM3, b.netStorageM3 - a.netStorageM3) &&
      close(v.accountedReductionM3, a.accountedDischargeM3 - b.accountedDischargeM3) &&
      close(v.peakReductionM3s, a.metrics.peakM3s - b.metrics.peakM3s) &&
      ((v.detention === undefined &&
        a.metrics.timing === undefined &&
        b.metrics.timing === undefined) ||
        (() => {
          const ta = a.metrics.timing,
            tb = b.metrics.timing,
            d = v.detention;
          if (!ta || !tb || !d) return false;
          const timings = [
            ['BASELINE', ta],
            ['STRATEGY', tb],
          ] as const;
          const blocker =
            timings.find(([, t]) => t.status === 'WITHHELD') ??
            timings.find(([, t]) => t.status === 'UNAVAILABLE');
          if (blocker)
            return (
              d.centroidDelaySeconds === null &&
              d.status === blocker[1].status &&
              d.reason === `${blocker[0]}_${blocker[1].reason}`
            );
          return (
            d.status === 'COMPARABLE' &&
            d.reason === null &&
            d.centroidDelaySeconds !== null &&
            ta.centroidSeconds !== null &&
            tb.centroidSeconds !== null &&
            close(d.centroidDelaySeconds, tb.centroidSeconds - ta.centroidSeconds)
          );
        })()) &&
      (!v.metricComparison ||
        (v.metricComparison.scope === 'SELECTED_INDEPENDENT_SURFACE' &&
          v.metricComparison.window?.kind === 'UTC' &&
          v.metricComparison.window.start === a.metrics.start &&
          v.metricComparison.window.end === a.metrics.end &&
          v.metricComparison.metrics.every((m) => {
            const raw =
              m.id === 'surfaceDischargeM3'
                ? [a.dischargeM3, b.dischargeM3]
                : m.id === 'surfaceAccountedVolumeM3'
                  ? [a.accountedDischargeM3, b.accountedDischargeM3]
                  : m.id === 'surfacePeakM3s'
                    ? [a.metrics.peakM3s, b.metrics.peakM3s]
                    : null;
            return raw
              ? m.status === 'COMPARABLE' && m.baseline === raw[0] && m.strategy === raw[1]
              : m.status === 'UNAVAILABLE';
          })))
    );
  });
export type RunoffComparisonData = z.infer<typeof runoffComparisonDto>;
