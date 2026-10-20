import { readPublicData } from '../../../shared/repository/publicDataCache';
import {
  topographyIndexDto,
  type TopographyEntry,
  type TopographyIndex,
} from '../dto/topographyDto';
import { TopographyError } from '../exception/TopographyError';
import type { TopographyBuffers } from '../entity/topography';
import type { Terrain } from '../../terrain/entity/terrain';
import { CITY_HASH } from '../../city/repository/cityRepository';
import { NATIVE_URBAN_HASH } from '../../urban/repository/nativeUrbanRepository';
export const TOPOGRAPHY_HASH = 'ec7854f72185d8023c15f95438f80cbfacfc2114690d21c705621bcf716b94f7';
let index: TopographyIndex | undefined;
export async function loadTopographyIndex(signal: AbortSignal) {
  if (index) return index;
  const parsed = topographyIndexDto.safeParse(
    await readPublicData('/data/seoul-features-v1/index.json', TOPOGRAPHY_HASH, 4194304, signal)
  );
  if (
    !parsed.success ||
    parsed.data.sourceCitySha256 !== CITY_HASH ||
    parsed.data.sourceStreetLifeSha256 !== NATIVE_URBAN_HASH
  )
    throw new TopographyError();
  if (!signal.aborted) index = parsed.data;
  return parsed.data;
}
type Job = {
  id: number;
  entry: TopographyEntry;
  layers: TopographyIndex['layers'];
  terrain: Terrain | null;
  terrainKey: number;
  plan: boolean;
  key: string;
  canceled: boolean;
  resolve: (data: TopographyBuffers) => void;
  reject: (error: Error) => void;
};
let worker: Worker | null = null,
  active: Job | null = null,
  sequence = 0,
  terrainSequence = 0,
  sentTerrain = -1,
  cacheBytes = 0;
const pending: Job[] = [],
  terrainIds = new WeakMap<object, number>(),
  cache = new Map<string, { data: TopographyBuffers; bytes: number }>();
const MAXIMUM = 96 * 1024 * 1024;
function stop() {
  worker?.terminate();
  worker = null;
  sentTerrain = -1;
  const jobs = [...(active ? [active] : []), ...pending.splice(0)];
  active = null;
  for (const job of jobs) if (!job.canceled) job.reject(new TopographyError());
}
function remember(key: string, data: TopographyBuffers) {
  const bytes =
    Object.values(data).reduce(
      (sum, value) => sum + (ArrayBuffer.isView(value) ? value.byteLength : 0),
      0
    ) +
    data.models.reduce((sum, model) => sum + model.matrices.byteLength, 0) +
    data.plan.reduce(
      (sum, value) => sum + 2 * (value.areas.length + value.lines.length + value.points.length),
      0
    );
  if (bytes > MAXIMUM) return;
  while (cacheBytes + bytes > MAXIMUM && cache.size) {
    const first = cache.keys().next().value!;
    cacheBytes -= cache.get(first)!.bytes;
    cache.delete(first);
  }
  cache.set(key, { data, bytes });
  cacheBytes += bytes;
}
function drain() {
  if (active || !pending.length) return;
  try {
    if (!worker) {
      worker = new Worker(new URL('../service/topographyGeometry.worker.ts', import.meta.url), {
        type: 'module',
      });
      const current = worker;
      worker.onmessage = (
        event: MessageEvent<{ id: number; data?: TopographyBuffers; failed?: boolean }>
      ) => {
        if (worker !== current || !active || active.id !== event.data.id) return;
        const job = active;
        active = null;
        if (!job.canceled) {
          if (event.data.data) {
            remember(job.key, event.data.data);
            job.resolve(event.data.data);
          } else job.reject(new TopographyError());
        }
        drain();
      };
      worker.onerror = stop;
      worker.onmessageerror = stop;
    }
    active = pending.shift()!;
    const { id, entry, layers, terrainKey, terrain, plan } = active;
    worker.postMessage({
      id,
      entry,
      layers,
      terrainKey,
      plan,
      ...(sentTerrain !== terrainKey ? { terrain } : {}),
    });
    sentTerrain = terrainKey;
  } catch {
    stop();
  }
}
export function requestTopographyTile(
  entry: TopographyEntry,
  layers: TopographyIndex['layers'],
  terrain: Terrain | null,
  plan: boolean,
  signal: AbortSignal
) {
  if (terrain && !terrainIds.has(terrain)) terrainIds.set(terrain, ++terrainSequence);
  const terrainKey = terrain ? terrainIds.get(terrain)! : 0,
    key = `${entry.sha256}:${terrainKey}:${plan}`;
  return new Promise<TopographyBuffers>((resolve, reject) => {
    if (signal.aborted) {
      reject(new DOMException('Aborted', 'AbortError'));
      return;
    }
    const found = cache.get(key);
    if (found) {
      cache.delete(key);
      cache.set(key, found);
      resolve(found.data);
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
      entry,
      layers,
      terrain,
      terrainKey,
      plan,
      key,
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
if (import.meta.hot)
  import.meta.hot.dispose(() => {
    stop();
    cache.clear();
    cacheBytes = 0;
    index = undefined;
  });
