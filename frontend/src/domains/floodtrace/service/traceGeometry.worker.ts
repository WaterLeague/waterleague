import { tracePositions } from './traceGeometryService';
import type { TraceTile } from '../entity/floodTrace';
import type { Terrain } from '../../terrain/entity/terrain';
self.onmessage = (
  event: MessageEvent<{ tiles: Pick<TraceTile, 'triangleVertices'>[]; terrain: Terrain | null }>
) => {
  try {
    const positions = tracePositions(event.data.tiles, event.data.terrain);
    self.postMessage({ positions }, { transfer: [positions.buffer] });
  } catch {
    self.postMessage({ failed: true });
  }
};
