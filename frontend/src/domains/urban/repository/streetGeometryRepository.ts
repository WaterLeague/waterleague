import type { Street } from '../entity/urban';
import type { Terrain } from '../../terrain/entity/terrain';
import type { StreetBuffers } from '../service/streetMeshService';
import { CityError } from '../../city/exception/CityError';
import { GeometryBufferCache } from '../../../shared/repository/geometryBufferCache';

type Job = {
  id: number;
  roads: Street[];
  terrain: Terrain | null;
  terrainKey: number;
  detail: boolean;
  center?: [number, number];
  parkingAisles: string[];
  variant: string;
  canceled: boolean;
  resolve: (data: StreetBuffers) => void;
  reject: (error: Error) => void;
};
let worker: Worker | null = null,
  active: Job | null = null,
  sequence = 0,
  terrainSequence = 0,
  sentTerrain = -1;
const pending: Job[] = [];
const terrains = new WeakMap<Terrain, number>();
const cache = new GeometryBufferCache<StreetBuffers>();

function fail() {
  if (worker) {
    worker.onmessage = null;
    worker.onerror = null;
    worker.onmessageerror = null;
    worker.terminate();
  }
  worker = null;
  sentTerrain = -1;
  const jobs = [...(active ? [active] : []), ...pending.splice(0)];
  active = null;
  for (const job of jobs) if (!job.canceled) job.reject(new CityError('INVALID_DATA'));
}
function drain() {
  if (active || !pending.length) return;
  try {
    if (!worker) {
      worker = new Worker(new URL('../service/streetGeometry.worker.ts', import.meta.url), {
        type: 'module',
      });
      const current = worker;
      worker.onmessage = (event: MessageEvent<{ id: number; data?: StreetBuffers }>) => {
        if (worker !== current || !active || active.id !== event.data.id) return;
        const job = active;
        active = null;
        if (!job.canceled) {
          if (event.data.data) {
            cache.put(job.roads, job.variant, event.data.data);
            job.resolve(event.data.data);
          } else job.reject(new CityError('INVALID_DATA'));
        }
        drain();
      };
      const failed = () => {
        if (worker === current) fail();
      };
      worker.onerror = failed;
      worker.onmessageerror = failed;
    }
    active = pending.shift()!;
    const { id, roads, terrain, terrainKey, detail, parkingAisles, center } = active;
    worker.postMessage({
      id,
      roads,
      terrainKey,
      detail,
      parkingAisles,
      center,
      ...(sentTerrain === terrainKey ? {} : { terrain }),
    });
    sentTerrain = terrainKey;
  } catch {
    fail();
  }
}
export function requestStreetMesh(
  roads: Street[],
  terrain: Terrain | null,
  detail: boolean,
  parkingAisles: string[],
  center: [number, number] | undefined,
  signal: AbortSignal
) {
  if (terrain && !terrains.has(terrain)) terrains.set(terrain, ++terrainSequence);
  const terrainKey = terrain ? terrains.get(terrain)! : 0;
  const detailCenter = detail ? center : undefined;
  const variant = JSON.stringify([terrainKey, detail, detailCenter, parkingAisles]);
  return new Promise<StreetBuffers>((resolve, reject) => {
    if (signal.aborted) {
      reject(new DOMException('Aborted', 'AbortError'));
      return;
    }
    const found = cache.get(roads, variant);
    if (found) {
      resolve(found);
      return;
    }
    const cancel = () => {
      job.canceled = true;
      const at = pending.indexOf(job);
      if (at >= 0) pending.splice(at, 1);
      if (active === job) worker?.postMessage({ id: job.id, cancel: true });
      job.reject(new DOMException('Aborted', 'AbortError'));
    };
    const job: Job = {
      id: ++sequence,
      roads,
      terrain,
      terrainKey,
      detail,
      center: detailCenter,
      parkingAisles,
      variant,
      canceled: false,
      resolve: (data) => {
        signal.removeEventListener('abort', cancel);
        resolve(data);
      },
      reject: (error) => {
        signal.removeEventListener('abort', cancel);
        reject(error);
      },
    };
    signal.addEventListener('abort', cancel, { once: true });
    pending.push(job);
    drain();
  });
}
if (import.meta.hot) import.meta.hot.dispose(fail);
