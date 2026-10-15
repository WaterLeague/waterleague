import { referenceDto } from '../dto/referenceDto';
import type { CpuReference } from '../entity/reference';
import { ReferenceDataError } from '../exception/ReferenceDataError';
export function mapReference(input: unknown): CpuReference {
  const parsed = referenceDto.safeParse(input);
  if (!parsed.success) throw new ReferenceDataError();
  const { report } = parsed.data;
  if (
    new Set(report.modelHashes).size !== report.modelHashes.length ||
    !report.modelHashes.includes(report.trainingModelHash) ||
    new Set(report.plans.map((p) => p.id)).size !== report.plans.length ||
    report.uniqueCandidateEvaluations > report.totalCandidateRequests ||
    report.totalCandidateRequests !== report.plans.reduce((n, p) => n + p.candidateEvaluations, 0)
  )
    throw new ReferenceDataError();
  for (const p of report.plans) {
    if (
      p.cost > p.budget ||
      new Set(p.placements.map((x) => x.cellId)).size !== p.placements.length ||
      p.evaluations.length !== report.modelHashes.length ||
      new Set(p.evaluations.map((e) => e.modelHash)).size !== p.evaluations.length ||
      p.sampleScoreRange.min !== Math.min(...p.evaluations.map((e) => e.score)) ||
      p.sampleScoreRange.max !== Math.max(...p.evaluations.map((e) => e.score))
    )
      throw new ReferenceDataError();
    for (const e of p.evaluations) {
      if (
        !report.modelHashes.includes(e.modelHash) ||
        (e.role === 'SEARCH_INPUT') !== (e.modelHash === report.trainingModelHash) ||
        e.baseline.accountedDischargeM3 <= 0 ||
        Math.abs(
          e.score -
            (100 * (e.baseline.accountedDischargeM3 - e.strategy.accountedDischargeM3)) /
              e.baseline.accountedDischargeM3
        ) > 0.000001
      )
        throw new ReferenceDataError();
    }
  }
  return parsed.data;
}
