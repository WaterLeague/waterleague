import { z } from 'zod';
import { initializationDto } from '../../physics/dto/initializationDto';
import { sensitivityMetricsDto } from '../../physics/dto/initializationSensitivityDto';

const hash = z.string().regex(/^[a-f0-9]{64}$/);
const catalogHash = z.literal('a9166ec93e6a6af4c460028f438c33fc67af0a1675502491e04f248c8e7dfd88');
const ids = ['FRESH', 'DUST_96_G', 'DUST_192_G'] as const;
const reference = {
  FRESH: { dustG: 0, permeabilityMmS: 3.49, conductivityMmH: 12564 },
  DUST_96_G: { dustG: 96, permeabilityMmS: 2.12, conductivityMmH: 7632 },
  DUST_192_G: { dustG: 192, permeabilityMmS: 1.4, conductivityMmH: 5040 },
};
const scenario = z
  .object({
    id: z.enum(ids),
    catalogId: z.literal('KWRA_TYPE_A_CLOGGING_REFERENCE_V1'),
    catalogSha256: catalogHash,
    dustG: z.number().finite().nonnegative(),
    permeabilityMmS: z.number().finite().positive(),
    conductivityMmH: z.number().finite().positive(),
    pavementDepthMm: z.literal(60),
    pavementPorosity: z.literal(0.2),
    imperviousFraction: z.literal(0),
    cloggingFactor: z.literal(0),
    timePolicy: z.literal('FIXED_THROUGH_SPINUP_AND_EVENT_NO_AUTOMATIC_AGING_OR_CLEANING'),
  })
  .refine((v) =>
    Object.entries(reference[v.id]).every(
      ([key, value]) => v[key as keyof typeof reference.FRESH] === value
    )
  );
const scenarioResult = z.discriminatedUnion('status', [
  z.object({
    status: z.literal('SUCCEEDED'),
    scenario,
    metrics: sensitivityMetricsDto,
    initialization: initializationDto.extend({
      method: z.literal('OBSERVED_7_DAY_CONTINUOUS_SPINUP_V1'),
      warmupMinutes: z.literal(10080),
      scoreExcludesWarmup: z.literal(true),
      evaluationStart: z.iso.datetime({ offset: true }),
    }),
    runoffContinuityPercent: z.number().finite().min(-1).max(1),
    evaluationBalanceResidualM3: z.number().finite(),
    inputSha256: hash,
  }),
  z.object({
    status: z.literal('FAILED'),
    scenario,
    phase: z.enum(['BASELINE', 'SCENARIO']),
    errorCode: z.string(),
  }),
]);
export const pavementMaintenanceDto = z
  .object({
    schemaVersion: z.literal(1),
    method: z.literal('FIXED_PERMEABILITY_MATERIAL_COMPARISON_V1'),
    scope: z.literal('INDEPENDENT_SURFACE_CONDUCTIVITY_SENSITIVITY'),
    status: z.enum(['SUCCEEDED', 'INCOMPLETE']),
    inputSha256: hash,
    sourcePolicySha256: hash,
    catalogSha256: catalogHash,
    source: z.object({
      title: z.string(),
      doi: z.literal('10.3741/JKWRA.2025.58.9.721'),
      url: z.literal('https://jkwra.or.kr/articles/pdf/N8x4/kwra-2025-058-09-0.pdf'),
      sha256: z.literal('67216d02adb3c1c632da7585756df150620d50b886a8cab2ff40d4113e3fe9df'),
      documentYear: z.literal(2025),
    }),
    specimen: z.object({
      widthMm: z.literal(200),
      lengthMm: z.literal(200),
      depthMm: z.literal(60),
      initialPorosity: z.literal(0.2),
      blockCount: z.literal(4),
      testAreaM2: z.literal(0.16),
    }),
    cellId: z.string(),
    areaM2: z.number().finite().positive(),
    facilityType: z.literal('PERMEABLE_PAVEMENT'),
    evaluationStart: z.iso.datetime({ offset: true }),
    evaluationEnd: z.iso.datetime({ offset: true }),
    cases: z.array(scenarioResult).length(3),
    differencesFromFresh: z
      .array(
        z.object({
          scenarioId: z.enum(['DUST_96_G', 'DUST_192_G']),
          minusFresh: sensitivityMetricsDto,
        })
      )
      .length(2)
      .nullable(),
    rankingEligible: z.literal(false),
    cleaningRecovery: z.object({
      status: z.literal('UNAVAILABLE'),
      reason: z.literal('MATCHED_MATERIAL_CLEANING_MEASUREMENTS_NOT_PUBLISHED'),
      value: z.null(),
    }),
    limitations: z.array(z.string()),
  })
  .refine((v) => {
    if (
      Date.parse(v.evaluationEnd) <= Date.parse(v.evaluationStart) ||
      v.cases.some((c, i) => c.scenario.id !== ids[i])
    )
      return false;
    const complete = v.cases.every((c) => c.status === 'SUCCEEDED');
    if ((v.status === 'SUCCEEDED') !== complete || (v.differencesFromFresh !== null) !== complete)
      return false;
    if (
      v.cases.some(
        (c) =>
          c.status === 'SUCCEEDED' &&
          Date.parse(c.initialization.evaluationStart) !== Date.parse(v.evaluationStart)
      )
    )
      return false;
    if (!v.differencesFromFresh) return true;
    const fresh = v.cases[0];
    if (fresh.status !== 'SUCCEEDED') return false;
    return v.differencesFromFresh.every((difference, i) => {
      const c = v.cases[i + 1];
      if (c.status !== 'SUCCEEDED' || difference.scenarioId !== c.scenario.id) return false;
      return Object.entries(c.metrics).every(([key, current]) => {
        const metric = key as keyof typeof c.metrics;
        const initial = fresh.metrics[metric];
        const delta = difference.minusFresh[metric];
        return initial === null || current === null
          ? delta === null
          : delta !== null && Math.abs(delta - (current - initial)) <= 1e-8;
      });
    });
  });
export type PavementMaintenanceComparison = z.infer<typeof pavementMaintenanceDto>;
