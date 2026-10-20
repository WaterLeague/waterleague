import type { Terrain } from '../../terrain/entity/terrain';
import type { Street } from '../entity/urban';
import { StreetMeshBuilder } from './streetMeshService';

const builder = new StreetMeshBuilder();
let active: { id: number; controller: AbortController } | null = null;
let terrain: Terrain | null = null,
  terrainKey = -1;
self.onmessage = async (
  event: MessageEvent<
    | { id: number; cancel: true }
    | {
        id: number;
        cancel?: false;
        roads: Street[];
        terrain?: Terrain | null;
        terrainKey: number;
        detail: boolean;
        parkingAisles: string[];
        center?: [number, number];
      }
  >
) => {
  const message = event.data;
  if (message.cancel) {
    if (active?.id === message.id) active.controller.abort();
    return;
  }
  const { id, roads, detail, parkingAisles, center } = message;
  const controller = new AbortController();
  active = { id, controller };
  try {
    if (message.terrain !== undefined) {
      terrain = message.terrain;
      terrainKey = message.terrainKey;
    }
    if (terrainKey !== message.terrainKey) throw new Error('지형 연결 누락');
    const data = await builder.build(
      roads,
      terrain,
      detail,
      parkingAisles,
      center,
      controller.signal
    );
    controller.signal.throwIfAborted();
    self.postMessage(
      { id, data },
      {
        transfer: [
          data.positions.buffer,
          data.colors.buffer,
          data.normals.buffer,
          data.bounds.buffer,
        ],
      }
    );
  } catch {
    self.postMessage({ id, failed: true });
  } finally {
    if (active?.id === id) active = null;
  }
};
