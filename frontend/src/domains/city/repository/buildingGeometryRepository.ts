import type { CityBuilding } from '../entity/city';
import type { BuildingMeshData } from '../service/buildingGeometryService';
import { CityError } from '../exception/CityError';
import { BuildingMeshCache, buildingMeshKey } from '../service/buildingMeshCache';

type Job = {
  id: number;
  buildings: CityBuilding[];
  cacheKey: string;
  resolve: (v: BuildingMeshData) => void;
  reject: (e: Error) => void;
  canceled: boolean;
};
let worker: Worker | null = null,
  active: Job | null = null,
  sequence = 0;
const pending: Job[] = [];
const cache = new BuildingMeshCache();

function stopWorker() {
  if (worker) {
    worker.onmessage = null;
    worker.onerror = null;
    worker.onmessageerror = null;
    worker.terminate();
  }
  worker = null;
}
function fail() {
  stopWorker();
  const jobs = [...(active ? [active] : []), ...pending.splice(0)];
  active = null;
  jobs.forEach((j) => {
    if (!j.canceled) j.reject(new CityError('INVALID_DATA'));
  });
}
function drain() {
  if (active || !pending.length) return;
  try {
    if (!worker) {
      worker = new Worker(new URL('../service/buildingGeometry.worker.ts', import.meta.url), {
        type: 'module',
      });
      const current = worker;
      worker.onmessage = (
        event: MessageEvent<{ id: number; data?: BuildingMeshData; failed?: boolean }>
      ) => {
        if (worker !== current) return;
        const job = active;
        if (!job || job.id !== event.data.id) return;
        active = null;
        if (!job.canceled) {
          if (event.data.data) {
            cache.put(job.cacheKey, event.data.data);
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
    worker.postMessage({ id: active.id, buildings: active.buildings });
  } catch {
    fail();
  }
}
export function requestBuildingMesh(buildings: CityBuilding[], signal: AbortSignal) {
  return new Promise<BuildingMeshData>((resolve, reject) => {
    if (signal.aborted) {
      reject(new DOMException('Aborted', 'AbortError'));
      return;
    }
    const cacheKey = buildingMeshKey(buildings);
    const cached = cache.get(cacheKey);
    if (cached) {
      resolve(cached);
      return;
    }
    const id = ++sequence;
    const cancel = () => {
      job.canceled = true;
      const index = pending.indexOf(job);
      if (index >= 0) pending.splice(index, 1);
      job.reject(new DOMException('Aborted', 'AbortError'));
      if (active === job) {
        // 취소 응답 뒤 다음 작업을 시작해 완성된 개별 건물 캐시를 보존한다.
        try {
          worker?.postMessage({ id: job.id, cancel: true });
        } catch {
          fail();
        }
      }
    };
    const job: Job = {
      id,
      buildings,
      cacheKey,
      canceled: false,
      resolve: (value) => {
        signal.removeEventListener('abort', cancel);
        resolve(value);
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
    fail();
    cache.clear();
  });
