import { expect, test } from 'vitest';
import { terrainHeight, terrainLine } from './terrainService';
import type { Terrain } from '../entity/terrain';
const terrain: Terrain = {
  width: 2,
  height: 2,
  origin: [0, 90],
  spacing: [90, -90],
  districtIds: [],
  heights: new Float32Array([10, 30, 50, 70]),
  districts: new Uint8Array(4),
  cover: new Uint8Array(4),
};
test('북쪽 원점·남쪽 행 방향의 높이 보간과 경계 제한', () => {
  expect(terrainHeight(terrain, [45, 45])).toBe(40);
  expect(terrainHeight(terrain, [0, 90])).toBe(10);
  expect(terrainHeight(terrain, [90, 0])).toBe(70);
  expect(terrainHeight(terrain, [-90, 180])).toBe(10);
});
test('긴 경계선의 고도 표본 분할과 장면 좌표 변환', () => {
  const points = terrainLine(
    terrain,
    [
      [0, 90],
      [90, 0],
    ],
    8
  );
  expect(points.length).toBe(12);
  expect(points.slice(0, 3)).toEqual([0, 18, -90]);
  expect(points.slice(3, 6)).toEqual([45, 48, -45]);
  expect(points.slice(-3)).toEqual([90, 78, -0]);
});
