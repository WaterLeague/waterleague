import { BuildingMeshBuilder } from './buildingMeshService';
import type { CityBuilding } from '../entity/city';

const builder = new BuildingMeshBuilder();
let active: { id: number; controller: AbortController } | null = null;
self.onmessage = async (
  event: MessageEvent<
    { id: number; cancel: true } | { id: number; cancel?: false; buildings: CityBuilding[] }
  >
) => {
  const message = event.data;
  if (message.cancel) {
    if (active?.id === message.id) active.controller.abort();
    return;
  }
  const { id, buildings } = message;
  const controller = new AbortController();
  active = { id, controller };
  try {
    const data = await builder.build(buildings, controller.signal);
    controller.signal.throwIfAborted();
    self.postMessage(
      { id, data },
      { transfer: [data.positions.buffer, data.normals.buffer, data.bounds.buffer] }
    );
  } catch {
    self.postMessage({ id, failed: true });
  } finally {
    if (active?.id === id) active = null;
  }
};
