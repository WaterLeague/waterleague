import { expect, test } from 'vitest';
import { Color } from 'three';
import type { Street } from '../entity/urban';
import { streetGeometry, streetHeight, streetOffsets } from './streetGeometryService';
import { sidewalkSides, streetLane } from './streetLifeService';
const road: Street = {
  id: 'way/1:0',
  class: 'residential',
  districtId: '1',
  widthM: 8,
  widthSource: 'DISPLAY_ASSUMPTION',
  walk: false,
  motor: true,
  oneway: 1,
  sidewalk: 'unknown',
  bridge: false,
  coordinates: [
    [0, 0],
    [30, 0],
    [30, 30],
  ],
};
test('연속 도로의 안팎 모서리 공유와 미확인·별도 보도의 중복 생성 방지', () => {
  expect(streetOffsets(road.coordinates, 4)).toEqual([
    [0, 4],
    [26, 4],
    [26, 30],
  ]);
  expect(sidewalkSides(road)).toEqual([false, false]);
  expect(
    sidewalkSides({ ...road, sidewalk: 'both', sidewalkLeft: 'separate', sidewalkRight: 'no' })
  ).toEqual([false, false]);
  const g = streetGeometry([road], null, false);
  expect(g.ends).toEqual([4]);
  expect(streetGeometry([{ ...road, sidewalk: 'separate' }], null, true).positions).toEqual(
    streetGeometry([road], null, true).positions
  );
});
test('교량·진입로·이동체가 원본 연결점의 같은 높이 사용', () => {
  const bridge = { ...road, bridge: true, elevationsM: [20, 20, 20] },
    ramp = {
      ...road,
      coordinates: [
        [30, 30],
        [30, 80],
      ] as [number, number][],
      elevationsM: [20, 16],
    };
  expect(streetHeight(null, [30, 30], bridge)).toBe(streetHeight(null, [30, 30], ramp));
  expect(streetHeight(null, [30, 55], ramp)).toBeCloseTo(18.004);
  expect(streetHeight(null, [33, 55], ramp, 0)).toBeCloseTo(18.004);
});
test('태그가 있는 횡단보도만 띠 노면 생성, 무표식 횡단·육교와 구분', () => {
  const crossing = {
    ...road,
    walk: true,
    motor: false,
    widthM: 3,
    footway: 'crossing',
    crossing: 'marked',
    coordinates: [
      [0, 0],
      [12, 0],
    ] as [number, number][],
  };
  const g = streetGeometry([crossing], null, true),
    white = new Color('#e8e5d4');
  expect(g.ends[0]).toBeGreaterThan(2);
  expect(g.colors[0]).toBeCloseTo(white.r);
  expect(streetGeometry([{ ...crossing, crossing: 'unmarked' }], null, true).positions.length).toBe(
    0
  );
  const footbridge = { ...crossing, footway: '', bridge: true, elevationsM: [10, 10] };
  expect(
    Math.min(
      ...Array.from(streetGeometry([footbridge], null, true).positions).filter(
        (_, i) => i % 3 === 1
      )
    )
  ).toBeGreaterThan(9);
});
test('차도와 겹친 보도는 잘린 다중 도형과 내부 구멍을 그대로 표시', () => {
  const walk = {
    ...road,
    motor: false,
    walk: true,
    walkPolygons: [
      [
        [
          [0, 0],
          [10, 0],
          [10, 10],
          [0, 10],
          [0, 0],
        ],
        [
          [3, 3],
          [3, 7],
          [7, 7],
          [7, 3],
          [3, 3],
        ],
      ],
    ] as [number, number][][][],
  };
  const g = streetGeometry([walk], null, true);
  let area = 0;
  for (let i = 0; i < g.positions.length; i += 9) {
    const p = g.positions;
    area +=
      Math.abs(
        (p[i + 3] - p[i]) * (p[i + 8] - p[i + 2]) - (p[i + 6] - p[i]) * (p[i + 5] - p[i + 2])
      ) / 2;
  }
  expect(area).toBeCloseTo(84);
  expect(streetGeometry([{ ...walk, walkPolygons: [] }], null, true).positions.length).toBe(0);
});
test('보도가 한쪽뿐인 도로에서 양방향 보행의 노면 위치 일치', () => {
  const one = { ...road, sidewalkLeft: 'yes', sidewalkRight: 'separate' };
  expect(streetLane(one, true, 1)).toBe(-4.7);
  expect(streetLane(one, true, -1)).toBe(4.7);
});

test('수직 교각의 두께를 양 수평축으로 표현', () => {
  const bridge = {
    ...road,
    bridge: true,
    coordinates: [
      [0, 0],
      [130, 0],
    ] as [number, number][],
    elevationsM: [20, 20],
  };
  const g = streetGeometry([bridge], null, true),
    xs = new Set<number>(),
    zs = new Set<number>();
  for (let i = 0; i < g.positions.length; i += 3)
    if (g.positions[i + 1] < 1 && g.positions[i + 2] > 0) {
      xs.add(g.positions[i]);
      zs.add(g.positions[i + 2]);
    }
  expect(xs.size).toBeGreaterThanOrEqual(2);
  expect(zs.size).toBeGreaterThanOrEqual(2);
});
