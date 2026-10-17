import type { Job, Placement, Version } from '../entity/game';

export function matchesEvaluatedDesign(
  job: Job | null,
  evaluated: Version | null,
  modelHash: string,
  placements: Placement[]
): boolean {
  if (
    !job ||
    !evaluated ||
    job.versionId !== evaluated.id ||
    job.modelHash !== modelHash ||
    evaluated.modelHash !== modelHash ||
    job.inputHash !== evaluated.inputHash
  )
    return false;
  if (placements.length !== evaluated.placements.length) return false;
  const current = new Map(placements.map((p) => [p.cellId, p]));
  if (current.size !== placements.length) return false;
  return evaluated.placements.every((p) => {
    const other = current.get(p.cellId);
    return other?.facilityType === p.facilityType && other.areaM2 === p.areaM2;
  });
}
