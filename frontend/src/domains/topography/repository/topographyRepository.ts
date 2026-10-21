import { NATIVE_TRANSPORT_HASH } from '../../urban/repository/nativeTransportDataSource';
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
import { NATIVE_BRIDGE_HASH } from '../../urban/repository/nativeBridgeVersion';
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
type Subscriber = { resolve: (data: TopographyBuffers) => void; reject: (error: Error) => void };
type Job = {
  id: number;
  entry: TopographyEntry;
  layers: TopographyIndex['layers'];
  terrain: Terrain | null;
  terrainKey: number;
  plan: boolean;
  key: string;
  subscribers: Set<Subscriber>;
};
let worker: Worker | null = null,
  sequence = 0,
  terrainSequence = 0,
  sentTerrain = -1,
  cacheBytes = 0;
const pending: Job[] = [],
  active = new Map<number, Job>(),
  jobs = new Map<string, Job>(),
  terrainIds = new WeakMap<object, number>(),
  cache = new Map<string, { data: TopographyBuffers; bytes: number }>();
const MAXIMUM = 96 * 1024 * 1024;
const CONCURRENCY = 4;
function stop() {
  worker?.terminate();
  worker = null;
  sentTerrain = -1;
  const all = [...jobs.values()];
  pending.length = 0;
  active.clear();
  jobs.clear();
  for (const job of all)
    for (const subscriber of job.subscribers) subscriber.reject(new TopographyError());
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
  const previous = cache.get(key);
  if (previous) {
    cacheBytes -= previous.bytes;
    cache.delete(key);
  }
  while (cacheBytes + bytes > MAXIMUM && cache.size) {
    const first = cache.keys().next().value!;
    cacheBytes -= cache.get(first)!.bytes;
    cache.delete(first);
  }
  cache.set(key, { data, bytes });
  cacheBytes += bytes;
}
function drain() {
  if (active.size >= CONCURRENCY || !pending.length) return;
  try {
    if (!worker) {
      worker = new Worker(new URL('../service/topographyGeometry.worker.ts', import.meta.url), {
        type: 'module',
      });
      const current = worker;
      worker.onmessage = (
        event: MessageEvent<{ id: number; data?: TopographyBuffers; failed?: boolean }>
      ) => {
        if (worker !== current) return;
        const job = active.get(event.data.id);
        if (!job) return;
        active.delete(job.id);
        jobs.delete(job.key);
        if (event.data.data) {
          remember(job.key, event.data.data);
          for (const subscriber of job.subscribers) subscriber.resolve(event.data.data);
        } else for (const subscriber of job.subscribers) subscriber.reject(new TopographyError());
        drain();
      };
      worker.onerror = worker.onmessageerror = () => {
        if (worker === current) stop();
      };
    }
    while (pending.length && active.size < CONCURRENCY) {
      const job = pending.shift()!;
      active.set(job.id, job);
      const { id, entry, layers, terrainKey, terrain, plan } = job;
      worker.postMessage({
        id,
        entry,
        layers,
        terrainKey,
        plan,
        ...(sentTerrain !== terrainKey ? { terrain } : {}),
      });
      sentTerrain = terrainKey;
    }
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
    key = `${entry.sha256}:${terrainKey}:${plan}:${plan ? '' : NATIVE_BRIDGE_HASH + NATIVE_TRANSPORT_HASH}`;
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
    let job = jobs.get(key);
    if (!job) {
      job = {
        id: ++sequence,
        entry,
        layers,
        terrain,
        terrainKey,
        plan,
        key,
        subscribers: new Set(),
      };
      jobs.set(key, job);
      pending.push(job);
    }
    const shared = job;
    const cancel = () => {
      shared.subscribers.delete(subscriber);
      const at = pending.indexOf(shared);
      if (!shared.subscribers.size && at >= 0) {
        pending.splice(at, 1);
        jobs.delete(key);
      }
      // 진행 중인 공개 타일은 마무리해 캐시에 보관하고 다음 시야 요청과 공유한다.
      subscriber.reject(new DOMException('Aborted', 'AbortError'));
    };
    const subscriber: Subscriber = {
      resolve: (data) => {
        signal.removeEventListener('abort', cancel);
        resolve(data);
      },
      reject: (error) => {
        signal.removeEventListener('abort', cancel);
        reject(error);
      },
    };
    shared.subscribers.add(subscriber);
    signal.addEventListener('abort', cancel, { once: true });
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
