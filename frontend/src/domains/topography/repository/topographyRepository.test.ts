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

test('공개 타일 4개 병렬 처리·대기 제한·역순 완료와 중복 응답 방어', async () => {
  const { requestTopographyTile } = await import('./topographyRepository');
  const signal = new AbortController().signal;
  const requests = index.tiles
    .slice(0, 6)
    .map((tile) => requestTopographyTile(tile, index.layers, null, false, signal));
  const worker = MockWorker.instances[0];
  expect(worker.postMessage).toHaveBeenCalledTimes(4);
  const messages = worker.postMessage.mock.calls.map(([message]) => message);
  const fourth = empty();
  fourth.counts.points = 4;
  worker.onmessage?.({ data: { id: messages[3].id, data: fourth } });
  expect(worker.postMessage).toHaveBeenCalledTimes(5);
  worker.onmessage?.({ data: { id: messages[3].id, data: empty() } });
  expect(worker.postMessage).toHaveBeenCalledTimes(5);
  for (const message of messages.slice(0, 3))
    worker.onmessage?.({ data: { id: message.id, data: empty() } });
  expect(worker.postMessage).toHaveBeenCalledTimes(6);
  for (const [message] of worker.postMessage.mock.calls.slice(4))
    worker.onmessage?.({ data: { id: message.id, data: empty() } });
  expect((await Promise.all(requests))[3]).toBe(fourth);
  expect(worker.postMessage.mock.calls.filter(([message]) => 'terrain' in message)).toHaveLength(1);
});

test('겹치는 시야의 같은 타일 요청 공유·이전 시야 취소 후 새 구독과 캐시 보존', async () => {
  const { requestTopographyTile } = await import('./topographyRepository');
  const old = new AbortController(),
    signal = new AbortController().signal;
  const first = requestTopographyTile(index.tiles[0], index.layers, null, false, old.signal);
  const rejected = expect(first).rejects.toMatchObject({ name: 'AbortError' });
  old.abort();
  const next = requestTopographyTile(index.tiles[0], index.layers, null, false, signal);
  const worker = MockWorker.instances[0],
    data = empty();
  expect(worker.postMessage).toHaveBeenCalledTimes(1);
  worker.onmessage?.({ data: { id: worker.postMessage.mock.calls[0][0].id, data } });
  await rejected;
  expect(await next).toBe(data);
  expect(await requestTopographyTile(index.tiles[0], index.layers, null, false, signal)).toBe(data);
  expect(worker.postMessage).toHaveBeenCalledTimes(1);
});

test('작업 스레드 실패 뒤 새 요청 복구·이전 스레드 지연 이벤트 제외', async () => {
  const { requestTopographyTile } = await import('./topographyRepository');
  const signal = new AbortController().signal;
  const first = requestTopographyTile(index.tiles[0], index.layers, null, false, signal);
  const failed = expect(first).rejects.toThrow();
  const old = MockWorker.instances[0],
    oldError = old.onerror!,
    oldResponse = old.onmessage!;
  oldError();
  await failed;
  const next = requestTopographyTile(index.tiles[0], index.layers, null, false, signal);
  const worker = MockWorker.instances[1],
    id = worker.postMessage.mock.calls[0][0].id;
  oldError();
  oldResponse({ data: { id, failed: true } });
  worker.onmessage?.({ data: { id, data: empty() } });
  await expect(next).resolves.toHaveProperty('counts');
  expect(worker.terminate).not.toHaveBeenCalled();
});
