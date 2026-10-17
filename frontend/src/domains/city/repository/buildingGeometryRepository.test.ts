import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import type { BuildingMeshData } from '../service/buildingGeometryService';

class TestWorker {
  static instances: TestWorker[] = [];
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: (() => void) | null = null;
  onmessageerror: (() => void) | null = null;
  postMessage = vi.fn();
  terminate = vi.fn();
  constructor() {
    TestWorker.instances.push(this);
  }
  complete(data: BuildingMeshData) {
    const { id } = this.postMessage.mock.lastCall![0];
    this.onmessage?.({ data: { id, data } } as MessageEvent);
  }
}
const mesh: BuildingMeshData = {
  positions: new Float32Array(9),
  normals: new Float32Array(9),
  ends: [1],
};
beforeEach(() => {
  vi.resetModules();
  TestWorker.instances = [];
  vi.stubGlobal('Worker', TestWorker);
});
afterEach(() => vi.unstubAllGlobals());

test('취소된 생성 작업 즉시 종료와 다음 작업 진행, 이전 오류의 새 작업 간섭 차단', async () => {
  const { requestBuildingMesh } = await import('./buildingGeometryRepository');
  const cancel = new AbortController();
  const first = requestBuildingMesh([], cancel.signal);
  const rejected = expect(first).rejects.toMatchObject({ name: 'AbortError' });
  const old = TestWorker.instances[0];
  const delayedError = old.onerror!;
  const next = requestBuildingMesh([], new AbortController().signal);
  expect(TestWorker.instances).toHaveLength(1);
  cancel.abort();
  await rejected;
  expect(old.terminate).toHaveBeenCalledOnce();
  expect(old.onmessage).toBeNull();
  const current = TestWorker.instances[1];
  expect(current.postMessage).toHaveBeenCalledOnce();
  delayedError();
  expect(current.terminate).not.toHaveBeenCalled();
  current.complete(mesh);
  await expect(next).resolves.toBe(mesh);
});

test('대기 작업 취소는 실행 중 형상을 중단하지 않으며 완료 후 스레드 재사용', async () => {
  const { requestBuildingMesh } = await import('./buildingGeometryRepository');
  const firstController = new AbortController();
  const first = requestBuildingMesh([], firstController.signal);
  const canceled = new AbortController();
  const second = requestBuildingMesh([], canceled.signal);
  const rejected = expect(second).rejects.toMatchObject({ name: 'AbortError' });
  canceled.abort();
  await rejected;
  const worker = TestWorker.instances[0];
  expect(worker.terminate).not.toHaveBeenCalled();
  worker.complete(mesh);
  await expect(first).resolves.toBe(mesh);
  firstController.abort();
  const third = requestBuildingMesh([], new AbortController().signal);
  expect(TestWorker.instances).toHaveLength(1);
  expect(worker.postMessage).toHaveBeenCalledTimes(2);
  worker.complete(mesh);
  await expect(third).resolves.toBe(mesh);
});
