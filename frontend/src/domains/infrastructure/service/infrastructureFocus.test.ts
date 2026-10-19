import { expect, test } from 'vitest';
import type { InfrastructureAsset } from '../entity/infrastructure';
import { infrastructureFocus } from './infrastructureFocus';
const asset = { center: [1200, 2400] } as InfrastructureAsset;
test('확대 상태의 목록 선택도 다른 공개 시설 위치로 이동', () => {
  const current = { center: [0, 0] as [number, number], distance: 18, heightM: 50 };
  const result = infrastructureFocus(asset, 1280, 600, current);
  expect(result.center).toEqual([1200, 2400]);
  expect(result.distance).toBe(18);
  expect(result.heightM).toBe(3);
  expect(current.center).toEqual([0, 0]);
});
test('위치점은 기호가 보이는 근접 배율, 공개 경계는 형상에 맞는 배율', () => {
  const current = { center: [0, 0] as [number, number], distance: 35000 };
  expect(infrastructureFocus(asset, 1280, 600, current).distance).toBe(55);
  const building = {
    ...asset,
    footprint: {
      polygons: [
        [
          [
            [0, 0],
            [40, 0],
            [40, 30],
            [0, 30],
            [0, 0],
          ],
        ],
      ],
      buildingId: 'W1',
      displayHeightM: 12,
    },
  } as InfrastructureAsset;
  const fitted = infrastructureFocus(building, 1280, 600, current);
  expect(fitted.center).toEqual([20, 15]);
  expect(fitted.heightM).toBe(6);
  expect(fitted.distance).toBeGreaterThanOrEqual(45);
  expect(fitted.distance).toBeLessThan(180);
});
