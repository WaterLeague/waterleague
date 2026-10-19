import { expect, test } from 'vitest';
import type { MapPolygons } from '../../catalog/service/mapGeometryService';
import { riverGeometry } from './riverGeometry';
test('수면 분할에서 원 외곽·섬 구멍·면적을 보존하고 임의 하천 유속을 만들지 않음', () => {
  const shape: MapPolygons = [
    [
      [
        [0, 0],
        [200, 0],
        [200, 200],
        [0, 200],
        [0, 0],
      ],
      [
        [80, 80],
        [80, 120],
        [120, 120],
        [120, 80],
        [80, 80],
      ],
    ],
  ];
  const value = riverGeometry([shape], null);
  let area = 0;
  for (let i = 0; i < value.positions.length; i += 9) {
    const [ax, , az, bx, , bz, cx, , cz] = value.positions.slice(i, i + 9);
    area += Math.abs((bx - ax) * (cz - az) - (bz - az) * (cx - ax)) / 2;
    const x = (ax + bx + cx) / 3,
      y = -(az + bz + cz) / 3;
    expect(x > 80 && x < 120 && y > 80 && y < 120).toBe(false);
  }
  expect(area).toBeCloseTo(200 * 200 - 40 * 40);
  expect(value.positions.length / 9).toBeGreaterThan(8);
  expect(value.flows.every((v) => v === 0)).toBe(true);
  expect(value.faces.every((v) => v === 1)).toBe(true);
});
