import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import snapshot from '../../../../public/data/seoul-features-v1/index.json';
import { topographyIndexDto } from '../dto/topographyDto';
const index = topographyIndexDto.parse(snapshot);
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
}
beforeEach(() => {
  vi.resetModules();
  MockWorker.instances = [];
  vi.stubGlobal('Worker', MockWorker);
});
afterEach(() => vi.unstubAllGlobals());
const empty = () => ({
  models: [],
  positions: new Float32Array(),
  colors: new Float32Array(),
  normals: new Float32Array(),
  lines: new Float32Array(),
  lineColors: new Float32Array(),
  plan: [],
  labels: [],
  counts: { points: 0, lines: 0, areas: 0 },
});
test('지도 이동으로 취소한 작업은 화면에 반영하지 않고 같은 작업 스레드를 재사용', async () => {
  const { requestTopographyTile } = await import('./topographyRepository');
  const old = new AbortController(),
    current = new AbortController();
  const first = requestTopographyTile(index.tiles[0], index.layers, null, false, old.signal);
  const rejected = expect(first).rejects.toThrow();
  old.abort();
  const next = requestTopographyTile(index.tiles[1], index.layers, null, false, current.signal);
  const worker = MockWorker.instances[0],
    firstId = worker.postMessage.mock.calls[0][0].id;
  worker.onmessage?.({ data: { id: firstId, failed: true } });
  const message = worker.postMessage.mock.calls.at(-1)![0];
  worker.onmessage?.({ data: { id: message.id, data: empty() } });
  await rejected;
  await expect(next).resolves.toHaveProperty('counts');
  expect(MockWorker.instances).toHaveLength(1);
  expect(worker.terminate).not.toHaveBeenCalled();
});
test('같은 원문·지형·모드의 재진입은 CPU 버퍼를 재사용', async () => {
  const { requestTopographyTile } = await import('./topographyRepository');
  const signal = new AbortController().signal,
    request = requestTopographyTile(index.tiles[0], index.layers, null, false, signal);
  const worker = MockWorker.instances[0],
    id = worker.postMessage.mock.calls[0][0].id,
    data = empty();
  worker.onmessage?.({ data: { id, data } });
  expect(await request).toBe(data);
  expect(await requestTopographyTile(index.tiles[0], index.layers, null, false, signal)).toBe(data);
  expect(worker.postMessage).toHaveBeenCalledTimes(1);
});
