import type { Lab } from '../../game/entity/game';
import type { ReferencePlan } from '../entity/reference';
export function canCopyReference(lab: Lab, plan: ReferencePlan) {
  return (
    plan.evaluations.some((e) => e.modelHash === lab.modelHash) &&
    plan.cost <= lab.model.budget &&
    plan.placements.every((p) => {
      const cell = lab.model.cells.find((c) => c.id === p.cellId);
      return cell && cell.allowedTypes.includes(p.facilityType) && p.areaM2 <= cell.maxAreaM2;
    }) &&
    plan.placements.reduce((n, p) => n + p.areaM2 * lab.model.unitCosts[p.facilityType], 0) ===
      plan.cost
  );
}
