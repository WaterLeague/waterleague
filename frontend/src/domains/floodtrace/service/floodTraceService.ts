import type { TraceEvent } from '../entity/floodTrace';
import type { PlanView } from '../../city/service/planNavigationService';

export function visibleTraceTiles(event: TraceEvent | undefined, camera: PlanView) {
  const [x, y] = camera.center,
    radius = camera.distance * 1.5;
  return (
    event?.tiles.filter(
      ({ bounds: [x0, y0, x1, y1] }) =>
        x0 <= x + radius && x1 >= x - radius && y0 <= y + radius && y1 >= y - radius
    ) ?? []
  );
}
export const traceColor = '#985b8e';
