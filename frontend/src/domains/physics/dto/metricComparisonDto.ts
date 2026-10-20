import { z } from 'zod';

const finite = z.number().finite();
export const metricDefinitions = {
  surfaceDischargeM3: ['m3', 'SELECTED_SURFACE_OUTLET', 'DECREASE'],
  surfaceAccountedVolumeM3: ['m3', 'SELECTED_SURFACE_OUTLET_WITH_NET_STORAGE', 'DECREASE'],
  surfacePeakM3s: ['m3/s', 'SELECTED_SURFACE_OUTLET', 'DECREASE'],
  networkOutflowM3: ['m3', 'ALL_NETWORK_EXTERNAL_OUTFALLS', 'DECREASE'],
  networkPeakM3s: ['m3/s', 'ALL_NETWORK_EXTERNAL_OUTFALLS', 'DECREASE'],
  networkFloodingM3: ['m3', 'NETWORK_EXTERNAL_NODE_FLOODING', 'DECREASE'],
  networkFloodingSeconds: ['s', 'NETWORK_EXTERNAL_NODE_FLOODING', 'DECREASE'],
  surfaceDepthAreaTimeM3Hours: ['m3*h', 'CONNECTED_SURFACE_GRID', 'DECREASE'],
  reusedVolumeM3: ['m3', 'VERIFIED_USE_DEMAND', 'INCREASE'],
} as const;
export type MetricId = keyof typeof metricDefinitions;
const id = z.enum(Object.keys(metricDefinitions) as [MetricId, ...MetricId[]]);
const reason = z.enum([
  'METRIC_MISSING',
  'NO_USE_DEMAND',
  'NO_SURFACE_GRID',
  'NO_CONVEYANCE_NETWORK',
  'NUMERICAL_FAILURE',
  'BOUNDARY_MISMATCH',
  'INCOMPLETE_RUN',
  'NOT_COLLECTED',
  'DIFFERENT_EVALUATION_BOUNDARY',
  'UNMODELED_COVER_RAIN',
]);
export const comparedMetricDto = z
  .object({
    id,
    unit: z.string(),
    boundary: z.string(),
    preferredDirection: z.enum(['DECREASE', 'INCREASE']),
    status: z.enum(['COMPARABLE', 'UNAVAILABLE', 'WITHHELD']),
    reason: reason.nullable(),
    baseline: finite.nullable(),
    strategy: finite.nullable(),
    signedImprovement: finite.nullable(),
    relativeImprovementPercent: finite.nullable(),
    relativeStatus: z.enum([
      'COMPUTED',
      'ZERO_BASELINE',
      'NEGATIVE_BASELINE',
      'NOT_COMPARABLE',
      'NUMERIC_RANGE_EXCEEDED',
    ]),
  })
  .superRefine((v, ctx) => {
    const [unit, boundary, direction] = metricDefinitions[v.id];
    let valid = v.unit === unit && v.boundary === boundary && v.preferredDirection === direction;
    if (v.status !== 'COMPARABLE') {
      valid &&=
        v.reason !== null &&
        v.signedImprovement === null &&
        v.relativeImprovementPercent === null &&
        v.relativeStatus === 'NOT_COMPARABLE' &&
        (v.status !== 'UNAVAILABLE' || (v.baseline === null && v.strategy === null));
    } else if (v.baseline === null || v.strategy === null) {
      valid = false;
    } else {
      const difference = (v.baseline - v.strategy) * (direction === 'DECREASE' ? 1 : -1);
      valid &&= v.reason === null && v.signedImprovement === difference;
      if (v.baseline <= 0) {
        valid &&=
          v.relativeImprovementPercent === null &&
          v.relativeStatus === (v.baseline === 0 ? 'ZERO_BASELINE' : 'NEGATIVE_BASELINE');
      } else {
        const numerator = difference * 100;
        const expected = Number.isFinite(numerator)
          ? numerator / v.baseline
          : (difference / v.baseline) * 100;
        const inRange = Number.isFinite(expected) && (expected !== 0 || difference === 0);
        valid &&= inRange
          ? v.relativeStatus === 'COMPUTED' &&
            v.relativeImprovementPercent !== null &&
            Math.abs(v.relativeImprovementPercent - expected) <=
              Math.max(Number.MIN_VALUE * 8, Math.abs(expected) * 1e-12)
          : v.relativeStatus === 'NUMERIC_RANGE_EXCEEDED' && v.relativeImprovementPercent === null;
      }
    }
    if (!valid)
      ctx.addIssue({ code: 'custom', message: '원 지표·단위·절대 차이·보조 비율 불일치' });
  });
const window = z.discriminatedUnion('kind', [
  z
    .object({
      kind: z.literal('UTC'),
      start: z.iso.datetime({ offset: true }),
      end: z.iso.datetime({ offset: true }),
    })
    .refine((v) => Date.parse(v.end) > Date.parse(v.start)),
  z
    .object({
      kind: z.literal('ELAPSED_SECONDS'),
      start: finite.nonnegative(),
      end: finite.positive(),
      specificationSha256: z.string().regex(/^[a-f0-9]{64}$/),
    })
    .refine((v) => v.end > v.start),
]);
export const metricComparisonDto = z
  .object({
    schemaVersion: z.literal(1),
    method: z.literal('SIGNED_ABSOLUTE_PRIMARY_RELATIVE_AUXILIARY_V1'),
    scope: z.enum(['SELECTED_INDEPENDENT_SURFACE', 'PUBLISHED_NETWORK_REFERENCE_DESIGN']),
    window: window.nullable(),
    primaryMetricId: z.literal('surfaceAccountedVolumeM3').nullable(),
    compositeScore: z.null(),
    relativeUsedForRanking: z.literal(false),
    metrics: z.array(comparedMetricDto).length(9),
  })
  .superRefine((v, ctx) => {
    const surface = v.scope === 'SELECTED_INDEPENDENT_SURFACE';
    const comparable = v.metrics.filter((m) => m.status === 'COMPARABLE');
    if (
      new Set(v.metrics.map((m) => m.id)).size !== 9 ||
      v.primaryMetricId !== (surface ? 'surfaceAccountedVolumeM3' : null) ||
      (surface && v.window?.kind !== 'UTC') ||
      (!surface && v.window !== null && v.window.kind !== 'ELAPSED_SECONDS') ||
      comparable.some((m) =>
        surface
          ? !m.id.startsWith('surface') || m.id === 'surfaceDepthAreaTimeM3Hours'
          : !['networkOutflowM3', 'networkPeakM3s', 'networkFloodingM3'].includes(m.id)
      ) ||
      (comparable.length > 0 && !v.window)
    )
      ctx.addIssue({ code: 'custom', message: '평가 범위·지표 집합·주 지표 불일치' });
  });
export type MetricComparison = z.infer<typeof metricComparisonDto>;
export type ComparedMetric = MetricComparison['metrics'][number];
