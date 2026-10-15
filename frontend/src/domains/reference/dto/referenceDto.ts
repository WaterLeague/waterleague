import { z } from 'zod';
const hash = z.string().regex(/^[a-f0-9]{64}$/);
const value = z.number().nonnegative();
const money = value.int().max(300000000);
const placement = z.object({
  cellId: z.string().min(1).max(30),
  facilityType: z.enum(['RAIN_GARDEN', 'PERMEABLE_PAVEMENT', 'GREEN_ROOF']),
  areaM2: z.number().positive(),
});
const metrics = z.object({
  accountedDischargeM3: value,
  runoffM3: value,
  finalStorageM3: value,
  runoffContinuityPercent: z.number().min(-1).max(1),
});
export const referenceDto = z.object({
  reportHash: hash,
  report: z.object({
    schemaVersion: z.literal(1),
    id: hash,
    kind: z.literal('CPU_REFERENCE'),
    official: z.literal(false),
    validationLevel: z.literal('EXPLORATORY'),
    currency: z.literal('KRW'),
    algorithm: z.literal('GREEDY_MARGINAL_DISCHARGE_PER_KRW_V1'),
    stepAreaM2: z.literal(10),
    trainingModelHash: hash,
    modelHashes: z.array(hash).min(2).max(20),
    uniqueCandidateEvaluations: z.number().int().positive().max(2000),
    totalCandidateRequests: z.number().int().positive().max(6000),
    createdAt: z.iso.datetime({ offset: true }),
    limitations: z.array(z.string().max(300)).min(1).max(20),
    plans: z
      .array(
        z.object({
          id: z.string().regex(/^cpu-[0-9]+$/),
          title: z.string().max(100),
          budget: money.positive(),
          cost: money,
          placements: z.array(placement).max(50),
          candidateEvaluations: z.number().int().positive().max(2000),
          stages: z
            .array(
              z.object({
                placements: z.array(placement).max(50),
                cost: money,
                accountedDischargeM3: value,
                incrementReductionM3: z.number().positive(),
              })
            )
            .max(2000),
          stopReason: z.enum(['EVALUATION_LIMIT', 'NO_POSITIVE_FEASIBLE_INCREMENT']),
          sampleScoreRange: z.object({ min: z.number().max(100), max: z.number().max(100) }),
          evaluations: z
            .array(
              z.object({
                modelHash: hash,
                modelTitle: z.string().max(200),
                role: z.enum(['SEARCH_INPUT', 'POST_SELECTION_COMPARISON']),
                rainfall: z.object({
                  stationId: z.string().max(10),
                  stationName: z.string().max(40),
                  start: z.iso.datetime({ offset: true }),
                  end: z.iso.datetime({ offset: true }),
                  totalDepthMm: value,
                }),
                score: z.number().max(100),
                baseline: metrics,
                strategy: metrics,
              })
            )
            .min(2)
            .max(20),
        })
      )
      .length(3),
  }),
});
