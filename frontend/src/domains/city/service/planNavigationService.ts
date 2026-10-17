import type { CityFocus } from '../entity/city';

export type PlanView = Pick<CityFocus, 'center' | 'distance'>;
export function initialPlanView(focus: CityFocus, bounds: number[]): PlanView {
  return focus.overview
    ? {
        center: [(bounds[0] + bounds[2]) / 2, (bounds[1] + bounds[3]) / 2],
        distance: Math.max(bounds[2] - bounds[0], bounds[3] - bounds[1]) / 2 + 1000,
      }
    : { center: focus.center, distance: focus.distance };
}
export function zoomPlanView(view: PlanView, anchor: [number, number], factor: number): PlanView {
  const distance = Math.max(25, Math.min(100000, view.distance * factor));
  const ratio = distance / view.distance;
  return {
    center: [
      anchor[0] + (view.center[0] - anchor[0]) * ratio,
      anchor[1] + (view.center[1] - anchor[1]) * ratio,
    ],
    distance,
  };
}
