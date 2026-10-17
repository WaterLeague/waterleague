import type { FacilityType, Lab, Placement } from '../entity/game';
import type { PlacementDraft, PlacementIssue } from '../entity/placementDraft';
import { totalArea } from '../../league/service/leagueService';
import { format, totalCost, won } from './gameService';

export function assessPlacementDraft(
  lab: Lab,
  placements: Placement[],
  selected: string | null,
  type: FacilityType,
  area: number,
  limits: {
    budget: number;
    allowedTypes: FacilityType[];
    placementLimit: number;
    areaLimitM2?: number | null;
  }
): PlacementDraft {
  const areaM2 = Math.round(area * 100) / 100;
  const cell = lab.model.cells.find((c) => c.id === selected);
  const rejected = (issue: PlacementIssue, message: string): PlacementDraft => ({
    areaM2,
    placement: null,
    issue,
    message,
    projectedCost: null,
  });
  if (!cell) return rejected('SELECT_CELL', '지도나 구역 목록에서 설치할 곳을 선택하세요.');
  if (!cell.allowedTypes.includes(type) || !limits.allowedTypes.includes(type))
    return rejected('FACILITY_NOT_ALLOWED', '이 구역과 도전 조건에서 허용한 시설을 선택하세요.');
  if (!Number.isFinite(areaM2) || areaM2 < 0.01)
    return rejected('INVALID_AREA', '설치 면적을 0.01 m² 이상 입력하세요.');
  if (areaM2 > cell.maxAreaM2)
    return rejected(
      'CELL_AREA_LIMIT',
      `이 구역에는 최대 ${format.format(cell.maxAreaM2)} m²까지 배치할 수 있습니다.`
    );
  const placement = { cellId: cell.id, facilityType: type, areaM2 };
  const next = [...placements.filter((p) => p.cellId !== cell.id), placement];
  if (next.length > limits.placementLimit)
    return rejected(
      'PLACEMENT_LIMIT',
      `최대 ${limits.placementLimit}개 구역까지 배치할 수 있습니다. 기존 시설을 변경하거나 제거하세요.`
    );
  const nextArea = totalArea(next);
  if (
    limits.areaLimitM2 != null &&
    Math.round(nextArea * 100) > Math.round(limits.areaLimitM2 * 100)
  )
    return rejected(
      'TOTAL_AREA_LIMIT',
      `합계 면적 상한 ${format.format(limits.areaLimitM2)} m²를 ${format.format(nextArea - limits.areaLimitM2)} m² 초과합니다.`
    );
  const projectedCost = totalCost(lab, next);
  if (projectedCost > limits.budget)
    return {
      ...rejected(
        'BUDGET_LIMIT',
        `예산을 ${won(projectedCost - limits.budget)} 초과합니다. 면적을 줄이거나 다른 배치를 조정하세요.`
      ),
      projectedCost,
    };
  return { areaM2, placement, issue: null, message: '', projectedCost };
}
