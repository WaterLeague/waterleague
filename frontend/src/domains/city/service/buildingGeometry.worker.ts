import { buildBuildingMesh } from './buildingGeometryService';
import type { CityBuilding } from '../entity/city';

self.onmessage = (event: MessageEvent<{ id: number; buildings: CityBuilding[] }>) => {
  const { id, buildings } = event.data;
  try {
    const data = buildBuildingMesh(buildings);
    self.postMessage(
      { id, data },
      { transfer: [data.positions.buffer, data.normals.buffer, data.bounds.buffer] }
    );
  } catch {
    self.postMessage({ id, failed: true });
  }
};
