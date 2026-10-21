import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import type { Street } from '../entity/urban';
import type { Terrain } from '../../terrain/entity/terrain';

class MockWorker {
  static instances: MockWorker[] = [];
  onmessage: ((event: unknown) => void) | null = null;
  onerror: (() => void) | null = null;
  onmessageerror: (() => void) | null = null;
  terminate = vi.fn();
  postMessage = vi.fn();
  constructor() {
    MockWorker.instances.push(this);
  }
  complete(id?: number) {
    const current = id ?? this.postMessage.mock.calls.at(-1)![0].id;
    this.onmessage?.({ data: { id: current, data: empty() } });
  }
}
const empty = () => ({
  positions: new Float32Array(),
  colors: new Float32Array(),
  normals: new Float32Array(),
  bounds: new Float32Array(),
  ends: [],
  sphere: [0, 0, 0, 0],
});
const roads: Street[] = [];
const terrain: Terrain = {
  width: 1,
  height: 1,
  origin: [0, 0],
  spacing: [1, 1],
  districtIds: [],
  heights: new Float32Array(1),
  districts: new Uint8Array(1),
  cover: new Uint8Array(1),
};
beforeEach(() => {
  vi.resetModules();
  MockWorker.instances = [];
  vi.stubGlobal('Worker', MockWorker);
});
afterEach(() => vi.unstubAllGlobals());

test('카메라 이동 시 작업 스레드와 지형 전송을 재사용하고 지형 교체 시 다시 전달', async () => {
  const { requestStreetMesh } = await import('./streetGeometryRepository');
  const signal = new AbortController().signal;
  const first = requestStreetMesh(roads, terrain, true, [], [0, 0], signal);
  const worker = MockWorker.instances[0];
  expect(worker.postMessage.mock.calls[0][0].terrain).toBe(terrain);
  expect(worker.postMessage.mock.calls[0][0].roads).toBe(roads);
  worker.complete();
  await first;
  const second = requestStreetMesh(roads, terrain, true, [], [500, 0], signal);
  expect(worker.postMessage.mock.calls[1][0]).not.toHaveProperty('terrain');
  expect(worker.postMessage.mock.calls[1][0]).not.toHaveProperty('roads');
  worker.complete();
  await second;
  const nextTerrain = structuredClone(terrain);
  const third = requestStreetMesh(roads, nextTerrain, true, [], [500, 0], signal);
  expect(worker.postMessage.mock.calls[2][0].terrain).toBe(nextTerrain);
  worker.complete();
  await third;
  expect(MockWorker.instances).toHaveLength(1);
  expect(worker.terminate).not.toHaveBeenCalled();
});

test('원거리 이동은 완료 메시 재사용, 이미 취소한 요청은 캐시가 있어도 거절', async () => {
  const { requestStreetMesh } = await import('./streetGeometryRepository');
  const signal = new AbortController().signal;
  const first = requestStreetMesh(roads, null, false, [], [0, 0], signal);
  const worker = MockWorker.instances[0];
  worker.complete();
  const data = await first;
  expect(await requestStreetMesh(roads, null, false, [], [5000, 0], signal)).toBe(data);
  expect(worker.postMessage).toHaveBeenCalledTimes(1);
  const canceled = new AbortController();
  canceled.abort();
  await expect(
    requestStreetMesh(roads, null, false, [], [0, 0], canceled.signal)
  ).rejects.toMatchObject({ name: 'AbortError' });
});

test('이전 결과·대기 작업 취소가 다음 도로 갱신을 덮어쓰지 않으며 완료 후 취소 무시', async () => {
  const { requestStreetMesh } = await import('./streetGeometryRepository');
  const old = new AbortController(),
    skip = new AbortController(),
    current = new AbortController();
  const first = requestStreetMesh(roads, null, true, [], [0, 0], old.signal);
  const rejected = expect(first).rejects.toMatchObject({ name: 'AbortError' });
  const canceled = requestStreetMesh(roads, null, true, [], [500, 0], skip.signal);
  const skipped = expect(canceled).rejects.toMatchObject({ name: 'AbortError' });
  const next = requestStreetMesh(roads, null, true, [], [1000, 0], current.signal);
  skip.abort();
  old.abort();
  const worker = MockWorker.instances[0],
    id = worker.postMessage.mock.calls[0][0].id;
  expect(worker.postMessage.mock.calls[1][0]).toEqual({ id, cancel: true });
  worker.complete(id);
  expect(worker.postMessage.mock.calls.at(-1)![0].center).toEqual([1000, 0]);
  worker.complete(id);
  worker.complete();
  const data = await next;
  await rejected;
  await skipped;
  current.abort();
  expect(worker.postMessage).toHaveBeenCalledTimes(3);
  expect(
    await requestStreetMesh(roads, null, true, [], [1000, 0], new AbortController().signal)
  ).toBe(data);
  expect(worker.terminate).not.toHaveBeenCalled();
});

test('오류 뒤 새 작업을 재개하고 이전 스레드의 늦은 오류와 결과를 무시', async () => {
  const { requestStreetMesh } = await import('./streetGeometryRepository');
  const signal = new AbortController().signal;
  const first = requestStreetMesh(roads, terrain, true, [], [0, 0], signal);
  const rejected = expect(first).rejects.toThrow();
  const worker = MockWorker.instances[0],
    delayedError = worker.onerror!,
    delayedResult = worker.onmessage!;
  worker.onerror?.();
  await rejected;
  const next = requestStreetMesh(roads, terrain, true, [], [500, 0], signal);
  const fresh = MockWorker.instances[1];
  delayedError();
  delayedResult({ data: { id: 2, data: empty() } });
  expect(fresh.terminate).not.toHaveBeenCalled();
  expect(fresh.postMessage.mock.calls[0][0].terrain).toBe(terrain);
  expect(fresh.postMessage.mock.calls[0][0].roads).toBe(roads);
  fresh.complete();
  await next;
  expect(worker.terminate).toHaveBeenCalledOnce();
});
