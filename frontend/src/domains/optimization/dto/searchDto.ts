import { z } from 'zod';
import { comparisonDto } from '../../comparison/dto/comparisonDto';
const hash = z.string().regex(/^[a-f0-9]{64}$/),
  time = z.iso.datetime({ offset: true });
const score = z.number().min(-99999999).max(100),
  cost = z.number().nonnegative().max(999999999999);
const count = z.number().int().min(0).max(50),
  arm = z.enum(['PATTERN', 'UNIFORM']);
const placement = comparisonDto.shape.sourceVersion.shape.placements.element;
const placements = z.array(placement).max(50);
const result = comparisonDto.shape.jobs.element.shape.result
  .unwrap()
  .extend({ modelHash: hash, inputHash: hash });
export const searchSettingsDto = z.object({
  topK: z.number().int().min(2).max(20),
  budgetKrw: cost.positive().int(),
  seed: z.number().int().min(0).max(2147483647),
  candidatesPerArm: z.number().int().min(1).max(4),
});
const armView = z.object({
  arm,
  total: count,
  queued: count,
  running: count,
  succeeded: count,
  failed: count,
  rejected: count,
  bestScore: score.nullable(),
});
export const searchSummaryDto = z.object({
  id: z.uuid(),
  modelHash: hash,
  settings: searchSettingsDto,
  createdAt: time,
  sourceBestScore: score,
  completeComparison: z.boolean(),
  arms: z.array(armView).length(2),
});
const sample = z.object({
  jobId: z.uuid(),
  versionId: z.uuid(),
  inputHash: hash,
  placementsSource: z.string().max(32768),
  score,
  costKrw: cost,
});
const generated = z.object({
  arm,
  ordinal: z.number().int().min(1).max(4),
  attempt: z.number().int().min(0).max(127),
  inputHash: hash,
  placementsSource: z.string().max(32768),
  placements,
  costKrw: cost,
});
export const generationDto = z.object({
  schemaVersion: z.literal(1),
  policy: z.literal('ELITE_CATEGORICAL_SEARCH_V1'),
  modelHash: hash,
  settings: searchSettingsDto,
  requestedCount: count.min(2),
  uniquePhysicalCount: count.min(2),
  trainingCount: count.min(2),
  cutoffScore: score,
  smoothing: z.literal(1),
  binPercentages: z.tuple([z.literal(25), z.literal(50), z.literal(75), z.literal(100)]),
  drawLimit: z.literal(128),
  sources: z
    .array(z.object({ sample, physicalHash: hash, placements, selected: z.boolean() }))
    .min(2)
    .max(50),
  distributions: z
    .array(
      z.object({
        cellId: z.string().min(1).max(30),
        options: z
          .array(
            z.object({
              key: z.string().max(80),
              facilityType: placement.shape.facilityType.nullable(),
              percent: z.number().int().min(0).max(100),
              areaM2: z.number().nonnegative(),
              costKrw: cost,
              observedCount: count,
              patternWeight: count.max(51),
            })
          )
          .min(1)
          .max(13),
      })
    )
    .min(1)
    .max(50),
  arms: z
    .array(
      z.object({
        arm,
        attempts: z.number().int().min(1).max(128),
        emptyRejected: z.number().int().min(0).max(128),
        sourceRejected: z.number().int().min(0).max(128),
        duplicateRejected: z.number().int().min(0).max(128),
      })
    )
    .length(2),
  candidates: z.array(generated).min(2).max(8),
  sharedCandidateCount: z.number().int().min(0).max(4),
});
export const searchDto = z.object({
  id: z.uuid(),
  organizationId: z.uuid(),
  requestHash: hash,
  modelHash: hash,
  provenanceHash: hash,
  createdAt: time,
  validationLevel: z.literal('EXPLORATORY'),
  official: z.literal(false),
  generation: generationDto,
  sourceBestScore: score,
  completeComparison: z.boolean(),
  arms: z.array(armView).length(2),
  candidates: z
    .array(
      z.object({
        id: z.uuid(),
        arm,
        ordinal: z.number().int().min(1).max(4),
        placements,
        modelHash: hash,
        inputHash: hash,
        costKrw: cost,
        state: z.enum(['QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED', 'REJECTED']),
        result: result.nullable(),
        score: score.nullable(),
        errorCode: z.string().max(100).nullable(),
        createdAt: time,
        finishedAt: time.nullable(),
      })
    )
    .min(2)
    .max(8),
});
