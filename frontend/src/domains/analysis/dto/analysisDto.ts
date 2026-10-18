import { z } from 'zod';
import { comparisonDto } from '../../comparison/dto/comparisonDto';
const hash = z.string().regex(/^[a-f0-9]{64}$/);
const count = z.number().int().min(0).max(50);
const score = z.number().max(100);
const cost = z.number().min(0).max(300000000);
const facility = z.enum([
  'RAIN_GARDEN',
  'PERMEABLE_PAVEMENT',
  'GREEN_ROOF',
  'BIORETENTION',
  'VEGETATIVE_SWALE',
]);
export const researchComparisonSummaryDto = z.object({
  id: z.uuid(),
  sourceJobId: z.uuid(),
  title: z.string().max(80),
  createdAt: z.iso.datetime({ offset: true }),
});
export const researchComparisonDto = z.object({
  id: z.uuid(),
  organizationId: z.uuid(),
  sourceJobId: z.uuid(),
  requestHash: hash,
  createdAt: z.iso.datetime({ offset: true }),
  sourceSimulation: comparisonDto.shape.jobs.element.omit({ strategyId: true }),
  comparison: comparisonDto,
});
export const patternAnalysisDto = z.object({
  modelHash: hash,
  method: z.literal('SELECTED_UNIQUE_PHYSICAL_TOP_K_WITH_TIES_V2'),
  requestedCount: count.min(1),
  uniqueInputCount: count.min(1),
  duplicateInputCount: count,
  topK: z.number().int().min(1).max(20),
  includedCount: count.min(1),
  cutoffScore: score,
  designs: z
    .array(z.object({ jobId: z.uuid(), inputHash: hash, physicalHash: hash, score, costKrw: cost }))
    .min(1)
    .max(50),
  placements: z
    .array(
      z.object({
        cellId: z.string().min(1).max(30),
        facilityType: facility,
        designCount: count.min(1),
        frequencyPercent: z.number().min(0).max(100),
        minimumAreaM2: z.number().positive(),
        maximumAreaM2: z.number().positive(),
        meanInstalledAreaM2: z.number().positive(),
        meanAllDesignAreaM2: z.number().positive(),
      })
    )
    .max(2500),
  facilityPairs: z
    .array(
      z.object({
        first: facility,
        second: facility,
        designCount: count,
        frequencyPercent: z.number().min(0).max(100),
      })
    )
    .length(3),
  minimumCostKrw: cost,
  maximumCostKrw: cost,
  minimumScore: score,
  maximumScore: score,
  limitations: z.array(z.string().min(1).max(1000)).min(1).max(20),
});
