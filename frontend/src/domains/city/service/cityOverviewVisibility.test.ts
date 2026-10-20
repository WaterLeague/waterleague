import { expect, test } from 'vitest';
import { overviewBuildings } from './cityOverviewVisibility';
import type { CityOverview } from '../repository/cityOverviewRepository';
test('확대 범위 밖과 상세 상한 밖 건물은 축소 배경을 유지', () => {
  const common = { districts: ['11110'], tileIds: ['0_0', '10_0'] };
  const coarse: CityOverview = {
    ...common,
    buildings: [
      [5, 5, 10, 10, 10, 0, 0],
      [10005, 5, 10, 10, 10, 0, 1],
    ],
  };
  const fine: CityOverview = {
    ...common,
    buildings: [
      [10005, 5, 5, 5, 8, 0, 1],
      [5, 5, 5, 5, 12, 0, 0],
    ],
  };
  const visible = overviewBuildings(coarse, fine, [5, 5], 20000, new Set(), 1);
  expect(visible).toContainEqual(fine.buildings[1]);
  expect(visible).toContainEqual(coarse.buildings[1]);
  expect(overviewBuildings(coarse, fine, [5, 5], 1000, new Set(['0_0']))).toEqual([
    coarse.buildings[1],
  ]);
});
