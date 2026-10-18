import { z } from 'zod';
import { initializationDto } from './initializationDto';

const value = z.number().finite();
export const sensitivityMetricsDto = z.object({
  initialSoilMoisture: value.nullable(),
  initialStorageM3: value,
  initialLidStorageM3: value.nullable(),
  initialSurfaceDepthMm: value.nullable(),
  initialPavementDepthMm: value.nullable(),
  initialStorageDepthMm: value.nullable(),
  evaluatedDischargeM3: value,
  evaluatedEvaporationM3: value,
  evaluatedInfiltrationM3: value,
  peakDischargeMean1MinM3s: value,
  contributionM3: value,
});
const condition = {
  days: z.literal(7),
  seedSaturationPercent: z.union([z.literal(0), z.literal(100)]),
};
const caseDto = z.discriminatedUnion('status', [
  z.object({
    ...condition,
    status: z.literal('SUCCEEDED'),
    metrics: sensitivityMetricsDto,
    initialization: initializationDto,
  }),
  z.object({ ...condition, status: z.literal('FAILED'), errorCode: z.string() }),
]);
export const initializationSensitivityDto = z
  .object({
    schemaVersion: z.union([z.literal(1), z.literal(2)]),
    method: z.enum([
      'OBSERVED_SPINUP_DURATION_SEED_COMPARISON_V1',
      'OBSERVED_SPINUP_FACILITY_STATE_COMPARISON_V2',
    ]),
    facilityType: z.string().optional(),
    seedPolicy: z
      .enum(['LID_SATURATION_BOUNDARIES', 'NOT_APPLICABLE_FIXED_EMPTY_SURFACE'])
      .optional(),
    scope: z.literal('INPUT_BOUND_INDEPENDENT_SURFACE_ONLY'),
    inputSha256: z.string().regex(/^[a-f0-9]{64}$/),
    cellId: z.string(),
    areaM2: value.positive(),
    evaluationStart: z.string().datetime({ offset: true }),
    evaluationEnd: z.string().datetime({ offset: true }),
    cases: z.array(caseDto).min(1).max(2),
    comparison: z.discriminatedUnion('status', [
      z.object({ status: z.literal('INCOMPLETE'), ranges: z.null(), seedDifferences: z.null() }),
      z.object({
        status: z.literal('MEASURED_NO_UNIVERSAL_CONVERGENCE_THRESHOLD'),
        seedDifferences: z
          .array(z.object({ days: z.literal(7), wetMinusDry: sensitivityMetricsDto }))
          .max(1),
      }),
    ]),
    limitations: z.array(z.string()),
  })
  .refine((v) => {
    const swale = v.facilityType === 'VEGETATIVE_SWALE';
    const count = swale ? 1 : 2;
    const versionValid =
      v.schemaVersion === 1
        ? !swale && !v.seedPolicy && v.method === 'OBSERVED_SPINUP_DURATION_SEED_COMPARISON_V1'
        : !!v.facilityType &&
          v.method === 'OBSERVED_SPINUP_FACILITY_STATE_COMPARISON_V2' &&
          v.seedPolicy ===
            (swale ? 'NOT_APPLICABLE_FIXED_EMPTY_SURFACE' : 'LID_SATURATION_BOUNDARIES');
    return (
      versionValid &&
      v.cases.length === count &&
      new Set(v.cases.map((c) => c.seedSaturationPercent)).size === count &&
      (!swale || v.cases[0].seedSaturationPercent === 0) &&
      (v.comparison.status === 'INCOMPLETE') === v.cases.some((c) => c.status === 'FAILED') &&
      (v.comparison.status === 'INCOMPLETE' ||
        v.comparison.seedDifferences.length === (swale ? 0 : 1))
    );
  });
export type InitializationSensitivityData = z.infer<typeof initializationSensitivityDto>;
export type SensitivityMetrics = z.infer<typeof sensitivityMetricsDto>;
