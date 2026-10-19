import { expect, test } from 'vitest';
import { PerspectiveCamera, Vector3 } from 'three';
import { mapNearPlane } from './cameraDepthService';

function depthValues(distance: number, near: number) {
  const camera = new PerspectiveCamera(45, 1.5, near, 250000);
  camera.position.set(0, distance * 0.8, distance * 0.6);
  camera.lookAt(0, 0, 0);
  camera.updateMatrixWorld();
  return [0.004, 0.008, 0.012, 0.016, 0.02].map((height) =>
    Math.round((new Vector3(0, height, 0).project(camera).z * 0.5 + 0.5) * (2 ** 24 - 1))
  );
}
test.each([180, 1600, 4500])(
  '지도 거리 %sm에서 보도·노면·차선·흔적·계산 수면의 24bit 깊이 순서 보존',
  (distance) => {
    const depths = depthValues(distance, mapNearPlane(distance, distance * 0.8));
    for (let i = 1; i < depths.length; i++) expect(depths[i]).toBeLessThan(depths[i - 1]);
  }
);
test('기존 고정 near의 깊이 소실 재현 및 낮은 시점의 전방 잘림 제한', () => {
  expect(new Set(depthValues(1600, 5)).size).toBeLessThan(5);
  expect(mapNearPlane(4500, 15)).toBe(7.5);
});
