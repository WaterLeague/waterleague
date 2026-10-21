import { loadCity, loadCityPlayRegions, loadCityTile } from '../repository/cityDataSource';
import type { CityDataRequest, CityDataReply } from '../repository/cityDataClient';
import { CityError } from '../exception/CityError';
const active = new Map<number, AbortController>();
self.onmessage = async ({
  data,
}: MessageEvent<{ id: number; cancel?: boolean; request?: CityDataRequest }>) => {
  if (data.cancel) {
    active.get(data.id)?.abort();
    return;
  }
  if (!data.request) return;
  const controller = new AbortController();
  active.set(data.id, controller);
  try {
    const request = data.request;
    // 공개 자료의 해제·해시·JSON·스키마 검사를 화면 스레드에서 분리한다.
    const value =
      request.kind === 'tile'
        ? await loadCityTile(request.entry, controller.signal)
        : request.kind === 'city'
          ? await loadCity(controller.signal)
          : await loadCityPlayRegions(controller.signal);
    if (!controller.signal.aborted)
      self.postMessage({ id: data.id, data: value } satisfies CityDataReply);
  } catch (error) {
    if (!controller.signal.aborted)
      self.postMessage({
        id: data.id,
        failed: error instanceof CityError ? error.kind : 'INVALID_DATA',
      } satisfies CityDataReply);
  } finally {
    active.delete(data.id);
  }
};
