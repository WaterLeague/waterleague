import { expect, it } from 'vitest';
import { initialPlanView, zoomPlanView, planBox, planScale } from './planNavigationService';

it('전체 보기에서 공개 영역을 포함하고 지역 선택은 지정 중심 유지', () => {
  const bounds = [100, 200, 5100, 4200];
  const focus = { center: [250, 300] as [number, number], distance: 180, key: 1 };
  expect(initialPlanView(focus, bounds)).toEqual({ center: [250, 300], distance: 180 });
  const view = initialPlanView({ ...focus, overview: true }, bounds);
  expect(view.center).toEqual([2600, 2200]);
  expect(view.distance).toBeGreaterThan(2500);
});
it('세로·가로 화면 전체를 채우고 3D 중심·확대 거리를 보존', () => {
  const view = { center: [5768, -1323] as [number, number], distance: 1000 };
  for (const aspect of [0.5, 1, 2.4]) {
    const box = planBox(view, aspect);
    expect(box.width / box.height).toBeCloseTo(aspect);
    expect(box.x + box.width / 2).toBeCloseTo(view.center[0]);
    expect(-(box.y + box.height / 2)).toBeCloseTo(view.center[1]);
    expect(box.height / 2 / planScale).toBeCloseTo(view.distance);
  }
});
it('확대·축소와 배율 제한에서도 마우스 위치의 지도 좌표 유지', () => {
  for (const factor of [0.001, 0.5, 2, 1000]) {
    const view = { center: [200000, 550000] as [number, number], distance: 1000 };
    const anchor: [number, number] = [200400, 549800];
    const next = zoomPlanView(view, anchor, factor);
    expect((anchor[0] - next.center[0]) / next.distance).toBeCloseTo(
      (anchor[0] - view.center[0]) / view.distance
    );
    expect((anchor[1] - next.center[1]) / next.distance).toBeCloseTo(
      (anchor[1] - view.center[1]) / view.distance
    );
    expect(next.distance).toBeGreaterThanOrEqual(180);
    expect(next.distance).toBeLessThanOrEqual(150000);
    expect(view.center).toEqual([200000, 550000]);
  }
});
