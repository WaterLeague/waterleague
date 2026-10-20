import { expect, it } from 'vitest';
import { PerspectiveCamera, Vector3 } from 'three';
import { siteFocus, selectionView } from './siteFocusService';
import { zoomPlanView } from './planNavigationService';

it('근접 지도 선택은 시야 전체 유지, 목록 선택은 확대 유지, 전체 보기 선택은 초점 이동', () => {
  const fitted = { center: [100, 200] as [number, number], distance: 194.4, heightM: 20 };
  const close = { center: [85, 190] as [number, number], distance: 18, heightM: 0 };
  expect(selectionView(fitted, close, true)).toBe(close);
  expect(selectionView(fitted, close)).toEqual({ ...fitted, distance: 18 });
  expect(selectionView(fitted, { ...close, distance: 35000 }, true)).toEqual(fitted);
  expect(close).toEqual({ center: [85, 190], distance: 18, heightM: 0 });
});

it('길쭉한 건물·대형 건물·고층 건물 전체를 화면과 HUD 여백 안에 포함', () => {
  for (const [width, height] of [
    [390, 540],
    [561, 578],
    [1440, 800],
  ]) {
    for (const [east, north, roof] of [
      [600, 20, 15],
      [20, 600, 15],
      [500, 400, 90],
      [65, 80, 555],
    ]) {
      const coordinates: [number, number][] = [
        [0, 0],
        [east, 0],
        [east, north],
        [0, north],
        [0, 0],
      ];
      const focus = siteFocus(
        { polygons: [[coordinates]], heightM: roof, kind: 'ROOF' },
        width,
        height
      );
      const target = new Vector3(focus.center[0], focus.heightM, -focus.center[1]);
      const camera = new PerspectiveCamera(45, width / height, 1, 200000);
      camera.position.copy(target).add(new Vector3(0, focus.distance * 0.8, focus.distance * 0.6));
      camera.lookAt(target);
      camera.updateMatrixWorld();
      for (const [x, y] of coordinates)
        for (const z of [0, roof]) {
          const point = new Vector3(x, z, -y).project(camera);
          expect(Math.abs(point.x)).toBeLessThan(0.82);
          expect(Math.abs(point.y)).toBeLessThan((height - 240) / height);
          expect(point.z).toBeGreaterThan(-1);
          expect(point.z).toBeLessThan(1);
        }
      expect(focus.heightM).toBe(roof / 2);
    }
  }
});

it('지상 시설은 지면을 보고 2D 확대 후에도 건물 목표 높이를 보존', () => {
  const coordinates: [number, number][] = [
    [0, 0],
    [30, 0],
    [30, 20],
    [0, 20],
  ];
  expect(
    siteFocus({ polygons: [[coordinates]], heightM: 40, kind: 'GROUND' }, 600, 600).heightM
  ).toBe(0);
  const focus = siteFocus({ polygons: [[coordinates]], heightM: 100, kind: 'ROOF' }, 600, 600);
  expect(zoomPlanView(focus, [10, 10], 1.5).heightM).toBe(50);
});
