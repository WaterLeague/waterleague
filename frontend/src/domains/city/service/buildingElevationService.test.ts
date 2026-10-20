import { expect, test } from 'vitest';
import { buildingBaseElevation } from './buildingElevationService';
import type { Terrain } from '../../terrain/entity/terrain';
test('경사지의 낮은 건물도 외곽 지형에 묻히지 않는 기준 높이 사용', () => {
  const terrain: Terrain = {
    width: 2,
    height: 2,
    origin: [0, 10],
    spacing: [10, -10],
    districtIds: ['11110'],
    heights: new Float32Array([0, 10, 0, 10]),
    districts: new Uint8Array(4).fill(1),
    cover: new Uint8Array(4),
  };
  const polygons: [number, number][][][] = [
    [
      [
        [0, 0],
        [10, 0],
        [10, 10],
        [0, 10],
        [0, 0],
      ],
    ],
  ];
  expect(buildingBaseElevation(terrain, polygons)).toBeCloseTo(10.03);
  expect(buildingBaseElevation(null, polygons)).toBe(0);
});
