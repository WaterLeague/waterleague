import { CityError } from '../exception/CityError';
import type { City, CityTile, TileEntry } from '../entity/city';
import type { CityPlayRegion } from '../dto/cityPlayDto';

export type CityDataRequest = { kind: 'city' | 'regions' } | { kind: 'tile'; entry: TileEntry };
export type CityDataResult = City | CityTile | CityPlayRegion[];
export type CityDataReply = {
  id: number;
  data?: CityDataResult;
  failed?: 'NETWORK' | 'INVALID_DATA';
};
type Pending = { resolve: (data: CityDataResult) => void; reject: (error: Error) => void };
let worker: Worker | null = null;
let sequence = 0;
const pending = new Map<number, Pending>();
function stop() {
  const previous = worker;
  worker = null;
  if (previous) {
    previous.onmessage = previous.onerror = previous.onmessageerror = null;
    previous.terminate();
  }
  const jobs = [...pending.values()];
  pending.clear();
  jobs.forEach((job) => job.reject(new CityError('INVALID_DATA')));
}
function getWorker() {
  if (worker) return worker;
  const current = new Worker(new URL('../service/cityData.worker.ts', import.meta.url), {
    type: 'module',
  });
  current.onmessage = ({ data: reply }: MessageEvent<CityDataReply>) => {
    if (worker !== current) return;
    const job = pending.get(reply.id);
    if (!job) return;
    pending.delete(reply.id);
    if (reply.data) job.resolve(reply.data);
    else job.reject(new CityError(reply.failed === 'NETWORK' ? 'NETWORK' : 'INVALID_DATA'));
  };
  current.onerror = current.onmessageerror = () => {
    if (worker === current) stop();
  };
  worker = current;
  return current;
}
export function requestCityData(request: CityDataRequest, signal: AbortSignal) {
  return new Promise<CityDataResult>((resolve, reject) => {
    if (signal.aborted) {
      reject(new DOMException('Aborted', 'AbortError'));
      return;
    }
    const id = ++sequence;
    const cancel = () => {
      pending.delete(id);
      signal.removeEventListener('abort', cancel);
      reject(new DOMException('Aborted', 'AbortError'));
      try {
        worker?.postMessage({ id, cancel: true });
      } catch {
        stop();
      }
    };
    const finish = <T>(action: (value: T) => void, value: T) => {
      signal.removeEventListener('abort', cancel);
      action(value);
    };
    signal.addEventListener('abort', cancel, { once: true });
    pending.set(id, {
      resolve: (data) => finish(resolve, data),
      reject: (error) => finish(reject, error),
    });
    try {
      getWorker().postMessage({ id, request });
    } catch {
      stop();
    }
  });
}
if (import.meta.hot) import.meta.hot.dispose(stop);
