import type { Placement } from '../entity/game';
import type { PlacementHistory, PlacementHistoryAction } from '../entity/placementHistory';

const HISTORY_LIMIT = 50;
const snapshot = (placements: Placement[]) => placements.map((p) => ({ ...p }));

function samePlacements(a: Placement[], b: Placement[]) {
  const byCell = new Map(b.map((p) => [p.cellId, p]));
  return (
    a.length === b.length &&
    byCell.size === b.length &&
    a.every((p) => {
      const other = byCell.get(p.cellId);
      return other?.facilityType === p.facilityType && other.areaM2 === p.areaM2;
    })
  );
}

export function placementHistoryReducer(
  state: PlacementHistory,
  action: PlacementHistoryAction
): PlacementHistory {
  switch (action.type) {
    case 'RESET':
      return { past: [], present: snapshot(action.placements), future: [] };
    case 'CLEAR_HISTORY':
      return { past: [], present: state.present, future: [] };
    case 'CHANGE':
      if (samePlacements(state.present, action.placements)) return state;
      return {
        past: [...state.past.slice(-(HISTORY_LIMIT - 1)), state.present],
        present: snapshot(action.placements),
        future: [],
      };
    case 'UNDO':
      if (!state.past.length) return state;
      return {
        past: state.past.slice(0, -1),
        present: state.past[state.past.length - 1],
        future: [state.present, ...state.future].slice(0, HISTORY_LIMIT),
      };
    case 'REDO':
      if (!state.future.length) return state;
      return {
        past: [...state.past.slice(-(HISTORY_LIMIT - 1)), state.present],
        present: state.future[0],
        future: state.future.slice(1),
      };
  }
}
