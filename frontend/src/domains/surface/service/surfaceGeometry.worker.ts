import { surfaceGeometry } from './surfaceGeometry';
import type { SurfaceFrame, SurfaceMetric } from '../entity/surface';
import type { Terrain } from '../../terrain/entity/terrain';
self.onmessage = (
  event: MessageEvent<{ frame: SurfaceFrame; metric: SurfaceMetric; terrain: Terrain | null }>
) => {
  try {
    const { positions, colors } = surfaceGeometry(
      event.data.frame,
      event.data.metric,
      event.data.terrain
    );
    self.postMessage({ positions, colors }, { transfer: [positions.buffer, colors.buffer] });
  } catch {
    self.postMessage({ failed: true });
  }
};
