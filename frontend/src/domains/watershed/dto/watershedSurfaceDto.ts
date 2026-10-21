import { z } from 'zod';

const hash = z.string().regex(/^[a-f0-9]{64}$/);
const n = z.number().finite();
const status = z.enum(['PASSED', 'FAILED']);
const profileHashes = {
  'seocho-surface-design-v1': '017a325234f482695cf8bcf4b9cd0eece772cf58dacdafdb389bd37159a2b0e7',
  'seocho-surface-design-v2': '94fca7deba98583792d05806c1f768047ffe4034b110894f09246dc9e2a7e6da',
} as const;
const parameters = z.object({
  openingDiameterM: n.positive(),
  dischargeCoefficient: n.positive().max(1),
  surchargeHeadM: n.positive(),
  surfaceOffsetM: n,
  boundaryType: z.literal('REFLECTIVE'),
  durationSeconds: z.literal(86339),
  maximumExchangeMilliseconds: z.literal(1000),
  frameIntervalMilliseconds: z.literal(60000),
  networkNumericalProfile: z.object({
    id: z.string(),
    options: z.record(z.string(), z.union([z.string(), n])),
  }),
});
export const surfaceConnectionDto = z
  .object({
    id: z.enum(['seocho-surface-design-v1', 'seocho-surface-design-v2']),
    profileSha256: hash,
  })
  .refine((v) => profileHashes[v.id] === v.profileSha256, '지표 계산 버전 불일치');
export const watershedSurfaceProfileDto = z.object({
  schemaVersion: z.literal(1),
  id: z.enum(['seocho-surface-design-v1', 'seocho-surface-design-v2']),
  method: z.literal('PUBLISHED_SURFACE_CONNECTION_EXPLORATION_V1'),
  title: z.string(),
  sourceCatalogSha256: hash,
  sourceFiles: z.record(z.string(), hash),
  parameters,
  allowedFacilityTypes: z
    .array(z.enum(['BIORETENTION', 'INFILTRATION_TRENCH', 'VEGETATIVE_SWALE']))
    .min(1),
  rankingEligible: z.literal(false),
  historicalReconstructionEligible: z.literal(false),
  limitations: z.array(z.string()).min(1),
});
const raw = z.object({
  outwardVolumeM3: n,
  peakOutwardM3s: n,
  depthAreaTimeM3Hours: n,
  maximumDepthM: n,
  maximumWetAreaM2: n,
  maximumWetDurationSeconds: n,
});
const context = z.object({
  scopeId: z.string(),
  modelGrade: z.literal('EXPLORATORY'),
  evidenceClass: z.literal('PUBLIC_DATA'),
  comparisonKind: z.literal('PAST_RAINFALL_STRESS_TEST'),
  effectAreaId: z.string(),
  scenarioSnapshotSha256: hash,
  forcingSha256: hash,
  engineSha256: hash,
  metricSpecificationSha256: hash,
});
const caseDto = z.object({
  id: z.enum(['baseline', 'strategy']),
  resultSha256: hash,
  numericalStatus: status,
  complete: z.boolean(),
  durationSeconds: n.positive(),
  context,
  raw,
  balance: z.object({ balanceResidualM3: n, exchangeCancellationResidualM3: n }).catchall(n),
  networkConvergence: z.object({
    method: z.literal('EPA_5_2_4_NATIVE_COUNTERS_READ_ONLY'),
    routingSteps: n.int().positive(),
    nonConvergedSteps: n.int().nonnegative(),
    nonConvergedPercent: n.min(0).max(100),
  }),
  networkRoutingContinuityPercent: n,
  networkNumericalStatus: status,
  surfaceNumericalStatus: status,
  calendarDurationSeconds: n.positive(),
  calendarShortfallSeconds: n.nonnegative(),
  finalMaximumDepthM: n.nonnegative(),
});
export const watershedSurfaceComparisonDto = z
  .object({
    schemaVersion: z.literal(1),
    classification: z.literal('PUBLIC_COUPLED_DESIGN_COMPARISON'),
    profileSha256: hash,
    designSha256: hash,
    numericalStatus: status,
    cases: z.array(caseDto).length(2),
    signedReduction: raw.nullable(),
    parameters,
    sourceFiles: z.record(z.string(), hash),
    rankingEligible: z.literal(false),
    historicalReconstructionEligible: z.literal(false),
    totalScore: z.null(),
    limitations: z.array(z.string()).min(1),
  })
  .superRefine((v, ctx) => {
    const options = v.parameters.networkNumericalProfile.options;
    const current = v.profileSha256 === profileHashes['seocho-surface-design-v2'];
    const legacy = v.profileSha256 === profileHashes['seocho-surface-design-v1'];
    if (
      (!current && !legacy) ||
      (current && (options.WET_STEP !== 1 || options.DRY_STEP !== 1)) ||
      (legacy && (options.WET_STEP !== undefined || options.DRY_STEP !== undefined))
    )
      ctx.addIssue({ code: 'custom', message: '지표 계산 수문 간격과 버전 불일치' });
    const [a, b] = v.cases;
    const passed = v.cases.every((c) => c.complete && c.numericalStatus === 'PASSED');
    if (
      a.id !== 'baseline' ||
      b.id !== 'strategy' ||
      JSON.stringify(a.context) !== JSON.stringify(b.context) ||
      passed !== (v.numericalStatus === 'PASSED') ||
      passed !== (v.signedReduction !== null) ||
      v.cases.some(
        (c) =>
          c.durationSeconds !== v.parameters.durationSeconds ||
          c.networkConvergence.nonConvergedSteps > c.networkConvergence.routingSteps ||
          Math.abs(
            c.networkConvergence.nonConvergedPercent -
              (100 * c.networkConvergence.nonConvergedSteps) / c.networkConvergence.routingSteps
          ) > 1e-10 ||
          (c.numericalStatus === 'PASSED' &&
            (c.networkNumericalStatus !== 'PASSED' ||
              c.surfaceNumericalStatus !== 'PASSED' ||
              c.networkConvergence.nonConvergedSteps !== 0 ||
              Math.abs(c.networkRoutingContinuityPercent) > 1)) ||
          Object.values(c.raw).some((value) => value < 0) ||
          c.finalMaximumDepthM > c.raw.maximumDepthM ||
          c.raw.maximumWetDurationSeconds > c.durationSeconds ||
          c.calendarDurationSeconds - c.calendarShortfallSeconds !== c.durationSeconds
      )
    )
      ctx.addIssue({ code: 'custom', message: '지표·관망 비교 조건 또는 계산 상태 불일치' });
    if (v.signedReduction)
      for (const key of Object.keys(a.raw) as (keyof typeof a.raw)[])
        if (Math.abs(v.signedReduction[key] - (a.raw[key] - b.raw[key])) > 1e-8)
          ctx.addIssue({ code: 'custom', message: '지표·관망 원값과 개선량 불일치' });
  });
export type WatershedSurfaceComparison = z.infer<typeof watershedSurfaceComparisonDto>;
