import { expect, test } from 'vitest';
import { streetPath } from './streetLifeService';
import {
  activeRailTrains,
  railLineKey,
  railServices,
  pairedRailDirections,
  trainCarriages,
} from './railLifeService';
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

test('평행 선로는 원 선형의 저장 방향과 관계없이 반대 방향 운행', () => {
  const a = streetPath({
    ...road,
    id: 'a',
    coordinates: [
      [0, 0],
      [400, 0],
    ],
  });
  const b = streetPath({
    ...road,
    id: 'b',
    coordinates: [
      [400, 4],
      [0, 4],
    ],
  });
  const directions = pairedRailDirections([a, b]);
  expect(directions.size).toBe(2);
  const first = trainCarriages(a, 10, directions.get('a'))[0];
  const second = trainCarriages(b, 10, directions.get('b'))[0];
  expect(Math.cos(first.center.angle - second.center.angle)).toBeCloseTo(-1);
});
test('단선은 편성 퇴장 뒤 방향을 교대하며 한 시각에 두 방향을 중첩하지 않음', () => {
  const path = streetPath(road),
    directions = new Set<number>();
  for (let seconds = 0; seconds < 150; seconds++) {
    const cars = trainCarriages(path, seconds);
    expect(new Set(cars.map((c) => c.direction)).size).toBeLessThanOrEqual(1);
    cars.forEach((c) => directions.add(c.direction));
  }
  expect([...directions].sort()).toEqual([-1, 1]);
});

test('여러 원 선분과 명칭 변형이 있어도 노선의 방향별 편성은 한 개이며 지도가 움직여도 운행 유지', () => {
  const paths = [0, 1000, 2000].flatMap((x, i) =>
    [0, 4].map((y, j) =>
      streetPath({
        ...road,
        id: `fragment:${i}:${j}`,
        nativeRailName: i === 0 ? '서울지하철7호선' : '지하철7호선',
        coordinates:
          j === 0
            ? [
                [x, y],
                [x + 400, y],
              ]
            : [
                [x + 400, y],
                [x, y],
              ],
      })
    )
  );
  expect(new Set(paths.map(railLineKey)).size).toBe(1);
  const services = railServices(paths);
  expect(services).toHaveLength(1);
  expect(services[0].runs).toHaveLength(3);
  const seen = new Set<string>();
  for (let time = 0; time < 600; time++) {
    const active = activeRailTrains(services, time).filter((t) => t.cars.length);
    expect(active.length).toBeLessThanOrEqual(2);
    active.forEach((t) => seen.add(t.path.road.id));
    if (active.length === 2)
      expect(Math.cos(active[0].cars[0].center.angle - active[1].cars[0].center.angle)).toBeCloseTo(
        -1
      );
    expect(activeRailTrains(railServices([...paths].reverse()), time)).toEqual(
      activeRailTrains(services, time)
    );
  }
  expect(seen.size).toBe(6);
});

test('서로 떨어진 단선 원본에는 다음 편성 진입 전 이전 편성 전체 퇴장', () => {
  const services = railServices(
    [0, 1000, 2000].map((x, i) =>
      streetPath({
        ...road,
        id: `single:${i}`,
        nativeRailName: '경춘선',
        coordinates: [
          [x, 0],
          [x + 300, 0],
        ],
      })
    )
  );
  for (let time = 0; time < 300; time++)
    expect(
      activeRailTrains(services, time).filter((t) => t.cars.length).length
    ).toBeLessThanOrEqual(1);
});
