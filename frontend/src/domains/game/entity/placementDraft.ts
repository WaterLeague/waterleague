import type { Placement } from './game';

export type PlacementIssue =
  | 'SELECT_CELL'
  | 'FACILITY_NOT_ALLOWED'
  | 'INVALID_AREA'
  | 'CELL_AREA_LIMIT'
  | 'PLACEMENT_LIMIT'
  | 'TOTAL_AREA_LIMIT'
  | 'BUDGET_LIMIT';

export interface PlacementDraft {
  areaM2: number;
  placement: Placement | null;
  issue: PlacementIssue | null;
  message: string;
  projectedCost: number | null;
}
