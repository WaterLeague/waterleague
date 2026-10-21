import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import type { CityTile } from '../../city/entity/city';
import type { Street } from '../entity/urban';
import { UrbanRoadSession } from './urbanRoadRepository';
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
}
beforeEach(() => {
  MockWorker.instances = [];
  vi.stubGlobal('Worker', MockWorker);
});
afterEach(() => vi.unstubAllGlobals());

test('같은 타일을 재전송하지 않고 최신 시야 응답에만 공유 도로·철도 적용', () => {
  const receive = vi.fn(),
    failed = vi.fn(),
    session = new UrbanRoadSession(receive, failed);
  const tiles: CityTile[] = [],
    roads: Street[] = [],
    railTraffic: Street[] = [];
  session.update(tiles, [0, 0], 1200);
  session.update(tiles, [10, 0], 1200);
  const worker = MockWorker.instances[0];
  expect(worker.postMessage.mock.calls[0][0].tiles).toEqual(tiles);
  expect(worker.postMessage.mock.calls[1][0]).not.toHaveProperty('tiles');
  worker.onmessage?.({ data: { id: 1, roads, railTraffic } });
  expect(receive).not.toHaveBeenCalled();
  worker.onmessage?.({ data: { id: 2 } });
  expect(receive).toHaveBeenCalledWith({ roads, railTraffic, railServices: [] });
  const previous = receive.mock.calls[0][0];
  session.update(tiles, [20, 0], 1200);
  worker.onmessage?.({ data: { id: 3 } });
  expect(receive.mock.calls[1][0]).toBe(previous);
  expect(failed).not.toHaveBeenCalled();
  session.dispose();
});

test('타일 갱신·오류 복구 때 자료 재전송, 오래된 스레드·해제 후 결과 제외', () => {
  const receive = vi.fn(),
    failed = vi.fn(),
    session = new UrbanRoadSession(receive, failed);
  const tiles: CityTile[] = [];
  session.update(tiles, [0, 0], 1200);
  const old = MockWorker.instances[0],
    stale = old.onmessage!,
    oldError = old.onerror!;
  oldError();
  expect(failed).toHaveBeenCalledOnce();
  session.update(tiles, [10, 0], 1200);
  const worker = MockWorker.instances[1];
  expect(worker.postMessage.mock.calls[0][0].tiles).toEqual(tiles);
  stale({ data: { id: 2, roads: [], railTraffic: [] } });
  oldError();
  expect(receive).not.toHaveBeenCalled();
  expect(worker.terminate).not.toHaveBeenCalled();
  const next: CityTile[] = [];
  session.update(next, [20, 0], 1200);
  expect(worker.postMessage.mock.calls[1][0].tiles).toEqual(next);
  session.dispose();
  worker.onmessage?.({ data: { id: 3, roads: [], railTraffic: [] } });
  session.update(next, [20, 0], 1200);
  expect(worker.postMessage).toHaveBeenCalledTimes(2);
  expect(receive).not.toHaveBeenCalled();
  expect(worker.terminate).toHaveBeenCalledOnce();
});

test('인접 시야 이동은 새 도로 타일만 전달하며 건물 자료는 별도 표시 경로에 유지', () => {
  const session = new UrbanRoadSession(vi.fn(), vi.fn());
  const a = {
    schemaVersion: 2,
    id: '0_0',
    buildings: [{ id: 'building-a' }],
    nativeFeatures: [],
  } as unknown as CityTile;
  const b = { ...a, id: '0_1' };
  const c = { ...a, id: '0_2' };
  session.update([a, b], [0, 0], 1200);
  const worker = MockWorker.instances[0];
  expect(
    worker.postMessage.mock.calls[0][0].tiles.map((tile: object) => 'buildings' in tile)
  ).toEqual([false, false]);
  session.update([b, c], [0, 10], 1200);
  const sent = worker.postMessage.mock.calls[1][0];
  expect(sent.tileIds).toEqual(['0_1', '0_2']);
  expect(sent.tiles.map((tile: { id: string }) => tile.id)).toEqual(['0_2']);
  expect(b.buildings).toHaveLength(1);
  session.dispose();
});
