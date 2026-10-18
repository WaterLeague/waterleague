import type { BudgetAccounting } from '../dto/budgetDto';
import type { FacilityType } from '../../game/entity/game';

export function designAccounting(
  policy: BudgetAccounting,
  costs: { facilityType: FacilityType; cost: number }[]
): BudgetAccounting {
  const used = new Map<FacilityType, number>();
  for (const item of costs) {
    if (
      !Number.isFinite(item.cost) ||
      item.cost < 0 ||
      !policy.facilities.some((f) => f.facilityType === item.facilityType)
    )
      throw new Error('설계 예산 항목 오류');
    used.set(item.facilityType, (used.get(item.facilityType) ?? 0) + Math.round(item.cost * 100));
  }
  const programs = policy.programs.map((p) => {
    const allocatedKrw =
      policy.facilities
        .filter((f) => f.programId === p.id)
        .reduce((n, f) => n + (used.get(f.facilityType) ?? 0), 0) / 100;
    return { ...p, allocatedKrw, remainingKrw: Math.max(0, p.limitKrw - allocatedKrw) };
  });
  return {
    version: policy.version,
    programs,
    facilities: policy.facilities.map((f) => {
      const program = programs.find((p) => p.id === f.programId);
      if (!program) throw new Error('설계 예산 사업 오류');
      const allocatedKrw = (used.get(f.facilityType) ?? 0) / 100;
      return {
        ...f,
        allocatedKrw,
        availableKrw: Math.min(
          program.remainingKrw,
          f.limitKrw === null ? Infinity : Math.max(0, f.limitKrw - allocatedKrw)
        ),
      };
    }),
  };
}
