import type { NativeBridgeGroup } from '../dto/nativeBridgeDto';
import { CityError } from '../../city/exception/CityError';
export { NATIVE_BRIDGE_HASH } from './nativeBridgeVersion';
let cache: NativeBridgeGroup[] | undefined;
export function loadNativeBridges(signal: AbortSignal): Promise<NativeBridgeGroup[]> {
  if (signal.aborted) return Promise.reject(new DOMException('Aborted', 'AbortError'));
  if (cache) return Promise.resolve(cache);
  return new Promise((resolve, reject) => {
    const worker = new Worker(new URL('../service/nativeBridgeData.worker.ts', import.meta.url), {
      type: 'module',
    });
    const finish = () => {
      signal.removeEventListener('abort', cancel);
      worker.terminate();
    };
    const cancel = () => {
      finish();
      reject(new DOMException('Aborted', 'AbortError'));
    };
    signal.addEventListener('abort', cancel, { once: true });
    worker.onmessage = (event: MessageEvent<{ groups?: NativeBridgeGroup[] }>) => {
      finish();
      if (!event.data.groups) {
        reject(new CityError('INVALID_DATA'));
        return;
      }
      cache = event.data.groups;
      resolve(cache);
    };
    worker.onerror = worker.onmessageerror = () => {
      finish();
      reject(new CityError('INVALID_DATA'));
    };
    worker.postMessage({ load: true });
  });
}
