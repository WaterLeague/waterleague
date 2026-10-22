import { describe, expect, it } from 'vitest';
import { PerspectiveCamera, Vector3 } from 'three';
import { overviewCamera } from './overviewCameraService';

describe('게임 전체 보기 카메라', () => {
  for (const [width, height, top] of [
    [1280, 570, 165],
    [375, 556, 267],
    [320, 450, 240],
  ]) {
    it(`${width}px 화면의 조작부와 예산창 사이에 활성 구 경계 수용`, () => {
      for (const bounds of [
        [-23000, -19000, 25000, 23000],
        [1000, 2000, 6000, 7500],
      ]) {
        const area = { left: 40, right: width - 40, top: top + 22, bottom: height - 122 };
        const view = overviewCamera(bounds, width, height, 45, area);
        const camera = new PerspectiveCamera(45, width / height, 10, 600000);
        const [x, y] = view.center;
        camera.position.set(x, view.distance * 0.8, -y + view.distance * 0.6);
        camera.lookAt(x, 0, -y);
        camera.updateMatrixWorld();
        for (const px of [bounds[0], bounds[2]])
          for (const py of [bounds[1], bounds[3]]) {
            const point = new Vector3(px, 0, -py).project(camera);
            const screenX = ((point.x + 1) * width) / 2;
            const screenY = ((1 - point.y) * height) / 2;
            expect(screenX).toBeGreaterThanOrEqual(area.left - 0.001);
            expect(screenX).toBeLessThanOrEqual(area.right + 0.001);
            expect(screenY).toBeGreaterThanOrEqual(area.top - 0.001);
            expect(screenY).toBeLessThanOrEqual(area.bottom + 0.001);
          }
      }
    });
  }
});
