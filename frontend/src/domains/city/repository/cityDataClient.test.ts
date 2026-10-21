import { afterEach, beforeEach, expect, test, vi } from 'vitest';
class MockWorker {
  static instances: MockWorker[] = [];
  onmessage: ((event: unknown) => void) | null = null;
  onerror: (() => void) | null = null;
  onmessageerror: (() => void) | null = null;
  postMessage = vi.fn();
  terminate = vi.fn();
  constructor() {
    MockWorker.instances.push(this);
  }
  complete(id: number, data: unknown) {
    this.onmessage?.({ data: { id, data } });
  }
}
beforeEach(() => {
  vi.resetModules();
  MockWorker.instances = [];
  vi.stubGlobal('Worker', MockWorker);
});
afterEach(() => vi.unstubAllGlobals());
test('하나의 지도 작업 스레드에서 병렬 응답을 요청별로 반환하고 취소한 늦은 결과 무시', async () => {
  const { requestCityData } = await import('./cityDataClient');
  const old = new AbortController(),
    fresh = new AbortController();
  const previous = requestCityData({ kind: 'city' }, old.signal);
  const rejected = expect(previous).rejects.toMatchObject({ name: 'AbortError' });
  const next = requestCityData({ kind: 'regions' }, fresh.signal);
  const worker = MockWorker.instances[0];
  const [first, second] = worker.postMessage.mock.calls.map(([m]) => m.id);
  old.abort();
  worker.complete(first, { wrong: true });
  worker.complete(second, [{ districtId: '11110' }]);
  expect(await next).toEqual([{ districtId: '11110' }]);
  await rejected;
  fresh.abort();
  expect(worker.postMessage.mock.calls.at(-1)?.[0]).toEqual({ id: first, cancel: true });
  expect(MockWorker.instances).toHaveLength(1);
});
test('스레드 오류는 모든 진행 요청을 정리하고 새 요청에서 복구하며 이전 응답 차단', async () => {
  const { requestCityData } = await import('./cityDataClient');
  const signal = new AbortController().signal;
  const a = requestCityData({ kind: 'city' }, signal),
    b = requestCityData({ kind: 'regions' }, signal);
  const failed = Promise.all([
    expect(a).rejects.toHaveProperty('name', 'CityError'),
    expect(b).rejects.toHaveProperty('name', 'CityError'),
  ]);
  const old = MockWorker.instances[0],
    stale = old.onmessage!;
  old.onerror?.();
  await failed;
  const next = requestCityData({ kind: 'regions' }, signal);
  const current = MockWorker.instances[1],
    id = current.postMessage.mock.calls[0][0].id;
  stale({ data: { id, data: ['오래된 응답'] } });
  current.complete(id, []);
  expect(await next).toEqual([]);
  expect(old.terminate).toHaveBeenCalledOnce();
  expect(current.terminate).not.toHaveBeenCalled();
});
test('같은 지도는 메모리에서 재사용하며 이미 취소된 요청은 캐시가 있어도 거절', async () => {
  const { loadCity } = await import('./cityRepository');
  const first = loadCity(new AbortController().signal);
  const worker = MockWorker.instances[0],
    id = worker.postMessage.mock.calls[0][0].id;
  worker.complete(id, { districts: [], tiles: [] });
  const city = await first;
  expect(await loadCity(new AbortController().signal)).toBe(city);
  const aborted = new AbortController();
  aborted.abort();
  await expect(loadCity(aborted.signal)).rejects.toHaveProperty('name', 'AbortError');
  expect(worker.postMessage).toHaveBeenCalledOnce();
});
