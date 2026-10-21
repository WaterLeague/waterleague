import { expect, it } from 'vitest';
import type { Street } from '../entity/urban';
import {
  distanceToStreet,
  movingPosition,
  pathPosition,
  streetPath,
  streetLane,
} from './streetLifeService';
import { streetGeometry } from './streetGeometryService';
import { populationAt } from './populationService';
const road: Street = {
  id: 'way/1:0',
  class: 'residential',
  districtId: '1',
  widthM: 8,
  widthSource: 'OSM_WIDTH_TAG',
  walk: false,
  motor: true,
  oneway: 1,
  sidewalk: 'both',
  bridge: false,
  coordinates: [
    [0, 0],
    [100, 0],
    [100, 100],
  ],
};
it('중심선 꺾임·구간 길이·우측 통행과 역방향 일방통행 보존', () => {
  const path = streetPath(road);
  expect(path.length).toBe(200);
  expect(pathPosition(path, 50, 2, 1)).toMatchObject({ x: 51, y: -2 });
  expect(pathPosition(path, 150, 2, 1)).toMatchObject({ x: 102, y: 49 });
  const reverse = streetPath({ ...road, oneway: -1 });
  const a = movingPosition(reverse, 0, 0.2, false),
    b = movingPosition(reverse, 1, 0.2, false);
  expect(Math.abs(a.x - 100)).toBeLessThanOrEqual(road.widthM / 2);
  expect(b.y).toBeLessThan(a.y);
});
it('양 끝점이 화면 밖인 긴 도로도 현재 시선과 가까우면 표시 대상', () => {
  const path = streetPath({
    ...road,
    coordinates: [
      [-2000, 0],
      [2000, 0],
    ],
  });
  expect(distanceToStreet(path, 0, 50)).toBe(50);
  expect(distanceToStreet(path, 2010, 0)).toBe(10);
});
it('도로·차선 표면이 지면 위에 위치하고 원 좌표 불변', () => {
  const original = JSON.stringify(road),
    mesh = streetGeometry([road], null, true);
  expect(mesh.positions.length).toBeGreaterThan(36);
  for (let i = 1; i < mesh.positions.length; i += 3) expect(mesh.positions[i]).toBeGreaterThan(0);
  expect(mesh.positions.length).toBe(mesh.colors.length);
  expect(JSON.stringify(road)).toBe(original);
});
it('보행자는 차선 밖의 보도에서 차량 일방통행과 독립적으로 이동', () => {
  const path = streetPath({
    ...road,
    coordinates: [
      [0, 0],
      [100, 0],
    ],
  });
  const east = movingPosition(path, 0, 0.8, true);
  const west = movingPosition(path, 0, 0.2, true);
  expect(east.y).toBeCloseTo(-4.7);
  expect(west.y).toBeCloseTo(4.7);
  expect(movingPosition(path, 1, 0.8, true).x).toBeGreaterThan(east.x);
  expect(movingPosition(path, 1, 0.2, true).x).toBeLessThan(west.x);
});
it('2022 사건 KST 시간대 적용과 다른 과거 연도의 미래 자료 대체 금지', () => {
  const data = {
    event2022: { '20220808:1': Array.from({ length: 24 }, (_, i) => i * 1000) },
    reference2025: { '0:1': Array(24).fill(9999) },
  };
  expect(populationAt(data, Date.parse('2022-08-08T09:00:00Z'), '1', true)?.people).toBe(18000);
  expect(populationAt(data, Date.parse('2011-07-27T09:00:00Z'), '1', true)).toBeNull();
  expect(populationAt(data, Date.parse('2026-10-19T09:00:00Z'), '1', false)).toMatchObject({
    people: 9999,
    evidence: 'REFERENCE_2025',
  });
});

it('원 차로 수에 맞는 차로 중앙과 양방향 우측 통행을 공유', () => {
  const source = {
    ...road,
    oneway: 0,
    nativeSourceRole: 'ROAD_CENTERLINE',
    widthM: 13,
    lanes: 4,
    coordinates: [
      [0, 0],
      [100, 0],
    ] as [number, number][],
  };
  expect(streetLane(source, false, 1, 0)).toBe(1.5);
  expect(streetLane(source, false, 1, 0.9)).toBe(4.5);
  const east = movingPosition(streetPath(source), 0, 0.8, false),
    west = movingPosition(streetPath(source), 0, 0.2, false);
  expect(east.y).toBeLessThan(0);
  expect(west.y).toBeGreaterThan(0);
  expect(movingPosition(streetPath(source), 1, 0.8, false).x).toBeGreaterThan(east.x);
  expect(movingPosition(streetPath(source), 1, 0.2, false).x).toBeLessThan(west.x);
});

it('꺾인 차로에서 이동체 좌표가 연속이며 모서리에서 옆 차로로 순간 이동하지 않음', () => {
  const p = streetPath(road),
    a = pathPosition(p, 99.999, 2, 1),
    b = pathPosition(p, 100.001, 2, 1);
  expect(Math.hypot(a.x - b.x, a.y - b.y)).toBeLessThan(0.01);
});
