import { expect, test } from 'vitest';
import { streetPath } from './streetLifeService';
import { trainCarriages } from './railLifeService';
import { submergedSourcePath, streetHeight } from './streetGeometryService';
import type { Street } from '../entity/urban';
const road: Street = {
  id: 'rail:test',
  class: 'railway',
  districtId: '',
  widthM: 0,
  widthSource: 'NOT_CONFIRMED',
  walk: false,
  motor: false,
  oneway: 0,
  sidewalk: '',
  bridge: false,
  coordinates: [
    [0, 0],
    [200, 0],
    [200, 200],
  ],
  nativeRailKind: 'subway',
};
test('열차는 원 선형의 연결된 구간에서 이동하고 각 객차가 곡선과 끝점을 따름', () => {
  const path = streetPath(road),
    a = trainCarriages(path, 0),
    b = trainCarriages(path, 1);
  expect(a.length).toBeGreaterThan(0);
  expect(b.length).toBeGreaterThan(0);
  expect(Math.abs(a[0].distance - b[0].distance)).toBeCloseTo(10);
  for (let time = 0; time < 100; time++)
    for (const c of trainCarriages(path, time)) {
      expect(c.distance).toBeGreaterThanOrEqual(9);
      expect(c.distance).toBeLessThanOrEqual(391);
      expect(c.center.y === 0 || c.center.x === 200).toBe(true);
      expect(c.front.y === 0 || c.front.x === 200).toBe(true);
      expect(c.back.y === 0 || c.back.x === 200).toBe(true);
    }
  expect(trainCarriages(path, 20)).toEqual(trainCarriages(path, 20));
});

test('철교 상판이 있는 열차만 수면 위에 배치하고 물속 원 선형에는 차량을 만들지 않음', () => {
  const water: [number, number][][][] = [
    [
      [
        [0, -20],
        [100, -20],
        [100, 20],
        [0, 20],
        [0, -20],
      ],
    ],
  ];
  const deck: [number, number][][][] = [
    [
      [
        [0, -3],
        [100, -3],
        [100, 3],
        [0, 3],
        [0, -3],
      ],
    ],
  ];
  const train: Street = {
    ...road,
    nativeGroundCutPolygons: water,
    nativeWaterDecks: [
      { polygons: deck, waterPolygons: water, deckPolygons: deck, deckLiftM: 6.5 },
    ],
  };
  expect(submergedSourcePath(train, null, [50, 10])).toBe(true);
  expect(submergedSourcePath(train, null, [50, 0])).toBe(false);
  expect(submergedSourcePath(train, null, [150, 0])).toBe(false);
  expect(streetHeight(null, [50, 0], train)).toBeCloseTo(6.516);
});
