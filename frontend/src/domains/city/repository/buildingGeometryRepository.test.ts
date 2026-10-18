import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { buildBuildingMesh } from '../service/buildingGeometryService';
import type { CityBuilding } from '../entity/city';

const building: CityBuilding = {
  id: 'way/1',
  heightM: 12,
  center: [15, 15],
  areaM2: 900,
  heightSource: 'OSM_HEIGHT_TAG',
  polygons: [
    [
      [
        [0, 0],
        [30, 0],
        [30, 30],
        [0, 30],
        [0, 0],
      ],
    ],
  ],
};
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
  complete() {
    const { id, buildings } = this.postMessage.mock.calls.at(-1)![0];
    this.onmessage?.({ data: { id, data: buildBuildingMesh(buildings) } });
  }
}
beforeEach(() => {
  vi.resetModules();
  MockWorker.instances = [];
  vi.stubGlobal('Worker', MockWorker);
});
afterEach(() => vi.unstubAllGlobals());

test('취소한 이전 스레드의 지연 오류가 다음 생성 작업을 중단하지 않음', async () => {
  const { requestBuildingMesh } = await import('./buildingGeometryRepository');
  const cancel = new AbortController();
  const first = requestBuildingMesh([building], cancel.signal);
  const rejected = expect(first).rejects.toMatchObject({ name: 'AbortError' });
  const old = MockWorker.instances[0],
    delayedError = old.onerror!;
  const next = requestBuildingMesh([{ ...building, heightM: 40 }], new AbortController().signal);
  cancel.abort();
  await rejected;
  expect(old.terminate).toHaveBeenCalledOnce();
  expect(old.onmessage).toBeNull();
  const current = MockWorker.instances[1];
  delayedError();
  expect(current.terminate).not.toHaveBeenCalled();
  current.complete();
  expect((await next).positions).toEqual(
    buildBuildingMesh([{ ...building, heightM: 40 }]).positions
  );
});

test('대기 작업 취소는 실행 작업을 중단하지 않으며 완료 후 스레드 재사용', async () => {
  const { requestBuildingMesh } = await import('./buildingGeometryRepository');
  const firstController = new AbortController();
  const first = requestBuildingMesh([building], firstController.signal);
  const cancel = new AbortController();
  const second = requestBuildingMesh([{ ...building, heightM: 20 }], cancel.signal);
  const rejected = expect(second).rejects.toMatchObject({ name: 'AbortError' });
  cancel.abort();
  await rejected;
  const worker = MockWorker.instances[0];
  expect(worker.terminate).not.toHaveBeenCalled();
  worker.complete();
  await first;
  firstController.abort();
  const third = requestBuildingMesh([{ ...building, heightM: 30 }], new AbortController().signal);
  expect(MockWorker.instances).toHaveLength(1);
  expect(worker.postMessage).toHaveBeenCalledTimes(2);
  worker.complete();
  await third;
});

test('2D·3D 재진입은 동일 메시를 즉시 반환하고 변경 높이는 별도 계산', async () => {
  const { requestBuildingMesh } = await import('./buildingGeometryRepository');
  const first = requestBuildingMesh([building], new AbortController().signal);
  const worker = MockWorker.instances[0];
  worker.complete();
  const mesh = await first;
  const again = await requestBuildingMesh(
    structuredClone([building]),
    new AbortController().signal
  );
  expect(again).toBe(mesh);
  expect(worker.postMessage).toHaveBeenCalledTimes(1);
  const updated = requestBuildingMesh([{ ...building, heightM: 20 }], new AbortController().signal);
  worker.complete();
  expect((await updated).positions).not.toEqual(mesh.positions);
  expect(worker.postMessage).toHaveBeenCalledTimes(2);
});

test('취소된 작업의 형상은 저장하지 않고 대기 작업과 기존 캐시는 보존', async () => {
  const { requestBuildingMesh } = await import('./buildingGeometryRepository');
  const cached = requestBuildingMesh([building], new AbortController().signal);
  MockWorker.instances[0].complete();
  const original = await cached;
  const controller = new AbortController();
  const canceled = requestBuildingMesh([{ ...building, heightM: 20 }], controller.signal);
  const rejected = expect(canceled).rejects.toMatchObject({ name: 'AbortError' });
  const pending = requestBuildingMesh([{ ...building, heightM: 30 }], new AbortController().signal);
  controller.abort();
  await rejected;
  expect(MockWorker.instances[0].terminate).toHaveBeenCalledTimes(1);
  MockWorker.instances[1].complete();
  await pending;
  expect(await requestBuildingMesh([building], new AbortController().signal)).toBe(original);
  const retry = requestBuildingMesh([{ ...building, heightM: 20 }], new AbortController().signal);
  expect(MockWorker.instances[1].postMessage).toHaveBeenCalledTimes(2);
  MockWorker.instances[1].complete();
  await retry;
  const alreadyAborted = new AbortController();
  alreadyAborted.abort();
  await expect(requestBuildingMesh([building], alreadyAborted.signal)).rejects.toMatchObject({
    name: 'AbortError',
  });
});
