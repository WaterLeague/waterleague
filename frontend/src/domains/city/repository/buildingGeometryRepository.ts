import type { CityBuilding } from '../entity/city';
import type { BuildingMeshData } from '../service/buildingGeometryService';
import { CityError } from '../exception/CityError';

type Job = {
  id: number;
  buildings: CityBuilding[];
  resolve: (v: BuildingMeshData) => void;
  reject: (e: Error) => void;
  canceled: boolean;
};
let worker: Worker | null = null,
  active: Job | null = null,
  sequence = 0;
const pending: Job[] = [];

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
          if (event.data.data) job.resolve(event.data.data);
          else job.reject(new CityError('INVALID_DATA'));
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
    const id = ++sequence;
    const cancel = () => {
      job.canceled = true;
      const index = pending.indexOf(job);
      if (index >= 0) pending.splice(index, 1);
      job.reject(new DOMException('Aborted', 'AbortError'));
      if (active === job) {
        // 동기 형상 계산은 메시지로 중단할 수 없으므로 이전 작업의 스레드를 종료한다.
        stopWorker();
        active = null;
        drain();
      }
    };
    const job: Job = {
      id,
      buildings,
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
if (import.meta.hot) import.meta.hot.dispose(fail);
