import type { Placement } from './game';

export interface PlacementHistory {
  past: Placement[][];
  present: Placement[];
  future: Placement[][];
}

export type PlacementHistoryAction =
  | { type: 'CHANGE' | 'RESET'; placements: Placement[] }
  | { type: 'UNDO' | 'REDO' | 'CLEAR_HISTORY' };
