import { comparisonDto, summaryDto } from '../dto/comparisonDto';
import { ComparisonDataError } from '../exception/ComparisonDataError';
import type { RainfallComparison, ComparisonSummary } from '../entity/comparison';
export function mapComparison(input: unknown): RainfallComparison {
  const parsed = comparisonDto.safeParse(input);
  if (!parsed.success) throw new ComparisonDataError();
  const d = parsed.data;
  if (
    d.sourceVersionId !== d.sourceVersion.id ||
    new Set(d.jobs.map((j) => j.id)).size !== d.jobs.length ||
    new Set(d.jobs.map((j) => j.modelHash)).size !== d.jobs.length ||
    new Set(d.jobs.map((j) => j.versionId)).size !== d.jobs.length
  )
    throw new ComparisonDataError();
  for (const j of d.jobs)
    if ((j.state === 'SUCCEEDED') !== (j.result !== null)) throw new ComparisonDataError();
  return d;
}
export function mapSummaries(input: unknown): ComparisonSummary[] {
  const p = summaryDto.array().max(50).safeParse(input);
  if (!p.success) throw new ComparisonDataError();
  return p.data;
}
