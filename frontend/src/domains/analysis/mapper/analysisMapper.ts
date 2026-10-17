import {
  researchComparisonDto,
  researchComparisonSummaryDto,
  patternAnalysisDto,
} from '../dto/analysisDto';
import { AnalysisDataError } from '../exception/AnalysisDataError';
import { mapComparison } from '../../comparison/mapper/comparisonMapper';
import type {
  ResearchComparison,
  ResearchComparisonSummary,
  PatternAnalysis,
} from '../entity/analysis';
export function mapResearchComparisons(input: unknown): ResearchComparisonSummary[] {
  const p = researchComparisonSummaryDto.array().max(50).safeParse(input);
  if (!p.success || new Set(p.data.map((d) => d.id)).size !== p.data.length)
    throw new AnalysisDataError();
  return p.data;
}
export function mapResearchComparison(input: unknown): ResearchComparison {
  const p = researchComparisonDto.safeParse(input);
  if (!p.success) throw new AnalysisDataError();
  const d = p.data,
    source = d.sourceSimulation,
    version = d.comparison.sourceVersion;
  if (
    d.sourceJobId !== source.id ||
    source.state !== 'SUCCEEDED' ||
    !source.result ||
    source.versionId !== version.id ||
    source.modelHash !== version.modelHash ||
    source.inputHash !== version.inputHash
  )
    throw new AnalysisDataError();
  return { ...d, comparison: mapComparison(d.comparison) };
}
export function mapPatternAnalysis(input: unknown): PatternAnalysis {
  const p = patternAnalysisDto.safeParse(input);
  if (!p.success) throw new AnalysisDataError();
  const d = p.data;
  if (
    d.uniqueInputCount + d.duplicateInputCount !== d.requestedCount ||
    d.includedCount !== d.designs.length ||
    d.includedCount > d.uniqueInputCount ||
    d.includedCount < Math.min(d.topK, d.uniqueInputCount) ||
    new Set(d.designs.map((v) => v.jobId)).size !== d.includedCount ||
    new Set(d.designs.map((v) => v.inputHash)).size !== d.includedCount ||
    new Set(d.designs.map((v) => v.physicalHash)).size !== d.includedCount ||
    d.cutoffScore !== Math.min(...d.designs.map((v) => v.score)) ||
    d.minimumScore !== d.cutoffScore ||
    d.maximumScore !== Math.max(...d.designs.map((v) => v.score)) ||
    d.minimumCostKrw !== Math.min(...d.designs.map((v) => v.costKrw)) ||
    d.maximumCostKrw !== Math.max(...d.designs.map((v) => v.costKrw)) ||
    new Set(d.placements.map((v) => v.cellId + ':' + v.facilityType)).size !==
      d.placements.length ||
    new Set(d.facilityPairs.map((v) => [v.first, v.second].sort().join(':'))).size !== 3
  )
    throw new AnalysisDataError();
  for (const v of [...d.placements, ...d.facilityPairs]) {
    if (
      v.designCount > d.includedCount ||
      Math.abs(v.frequencyPercent - (v.designCount / d.includedCount) * 100) > 0.00501
    )
      throw new AnalysisDataError();
  }
  for (const v of d.placements) {
    if (
      v.minimumAreaM2 > v.maximumAreaM2 ||
      v.meanInstalledAreaM2 < v.minimumAreaM2 - 0.000051 ||
      v.meanInstalledAreaM2 > v.maximumAreaM2 + 0.000051 ||
      Math.abs(v.meanAllDesignAreaM2 - (v.meanInstalledAreaM2 * v.designCount) / d.includedCount) >
        0.000101
    )
      throw new AnalysisDataError();
  }
  if (d.facilityPairs.some((v) => v.first === v.second)) throw new AnalysisDataError();
  return d;
}
