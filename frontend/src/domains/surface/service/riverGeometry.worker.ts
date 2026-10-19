import { riverGeometry } from './riverGeometry';
import type { MapPolygons } from '../../catalog/service/mapGeometryService';
import type { Terrain } from '../../terrain/entity/terrain';
self.onmessage = (event: MessageEvent<{ surfaces: MapPolygons[]; terrain: Terrain | null }>) => {
  try {
    const data = riverGeometry(event.data.surfaces, event.data.terrain);
    self.postMessage(data, { transfer: Object.values(data).map((value) => value.buffer) });
  } catch {
    self.postMessage({ failed: true });
  }
};
