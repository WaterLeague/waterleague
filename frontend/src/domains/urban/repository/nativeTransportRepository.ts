import type { NativeTransport } from '../dto/nativeTransportDto';
import { CityError } from '../../city/exception/CityError';
let cache: NativeTransport | undefined;
export function loadNativeTransport(signal: AbortSignal): Promise<NativeTransport> {
  if (signal.aborted) return Promise.reject(new DOMException('Aborted', 'AbortError'));
  if (cache) return Promise.resolve(cache);
  return new Promise((resolve, reject) => {
    const worker = new Worker(
      new URL('../service/nativeTransportData.worker.ts', import.meta.url),
      { type: 'module' }
    );
    const finish = () => {
      signal.removeEventListener('abort', cancel);
      worker.terminate();
    };
    const cancel = () => {
      finish();
      reject(new DOMException('Aborted', 'AbortError'));
    };
    signal.addEventListener('abort', cancel, { once: true });
    worker.onmessage = (event: MessageEvent<{ data?: NativeTransport }>) => {
      finish();
      if (!event.data.data) {
        reject(new CityError('INVALID_DATA'));
        return;
      }
      cache = event.data.data;
      resolve(cache);
    };
    worker.onerror = worker.onmessageerror = () => {
      finish();
      reject(new CityError('INVALID_DATA'));
    };
    worker.postMessage({ load: true });
  });
}
