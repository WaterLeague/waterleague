import type { CityFocus } from '../entity/city';
import { minimumMapDistance } from './cameraDepthService';

export type PlanView = Pick<CityFocus, 'center' | 'distance' | 'heightM'>;
export const planScale = Math.tan(Math.PI / 8);
export function planBox(view: PlanView, aspect: number) {
  const halfHeight = view.distance * planScale;
  return {
    x: view.center[0] - halfHeight * aspect,
    y: -view.center[1] - halfHeight,
    width: halfHeight * aspect * 2,
    height: halfHeight * 2,
  };
}
export function initialPlanView(focus: CityFocus, bounds: number[], aspect = 1): PlanView {
  return focus.overview
    ? {
        center: [(bounds[0] + bounds[2]) / 2, (bounds[1] + bounds[3]) / 2],
        distance:
          (Math.max((bounds[2] - bounds[0]) / aspect, bounds[3] - bounds[1]) / 2 + 1000) /
          planScale,
      }
    : {
        center: focus.center,
        distance: focus.distance,
        ...(focus.heightM !== undefined ? { heightM: focus.heightM } : {}),
      };
}
export function zoomPlanView(view: PlanView, anchor: [number, number], factor: number): PlanView {
  const distance = Math.max(minimumMapDistance, Math.min(150000, view.distance * factor));
  const ratio = distance / view.distance;
  return {
    ...view,
    center: [
      anchor[0] + (view.center[0] - anchor[0]) * ratio,
      anchor[1] + (view.center[1] - anchor[1]) * ratio,
    ],
    distance,
  };
}
