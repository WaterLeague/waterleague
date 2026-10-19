import { expect, test } from 'vitest';
import {
  streetGeometry,
  streetHeight,
  bridgeDeckHeight,
  bridgeDeckThickness,
} from './streetGeometryService';
import type { Street } from '../entity/urban';

const road: Street = {
  id: 'way/1:0',
  class: 'service',
  districtId: '1',
  widthM: 8,
  widthSource: 'DISPLAY_ASSUMPTION',
  walk: false,
  motor: true,
  oneway: 0,
  sidewalk: 'unknown',
  bridge: false,
  coordinates: [
    [0, 0],
    [50, 0],
  ],
};

test('주차장 내부 통로에는 일반 도로의 가상 보도·중앙 차선 미생성', () => {
  const geometry = streetGeometry([road], null, true, [road.id]);
  const heights = Array.from(geometry.positions).filter((_, i) => i % 3 === 1);
  expect(heights.every((height) => Math.abs(height - 0.008) < 1e-6)).toBe(true);
  const sides = Array.from(geometry.positions).filter((_, i) => i % 3 === 2);
  expect(Math.max(...sides.map(Math.abs))).toBe(4);
  expect(geometry.ends).toEqual([2]);
});

test('고가도로 상판·측면·난간과 차량이 같은 교량 높이 사용', () => {
  const geometry = streetGeometry([{ ...road, bridge: true, sidewalk: 'no' }], null, true);
  const heights = Array.from(geometry.positions).filter((_, i) => i % 3 === 1);
  expect(Math.min(...heights)).toBeCloseTo(bridgeDeckHeight - bridgeDeckThickness);
  expect(Math.max(...heights)).toBeCloseTo(bridgeDeckHeight + 0.96);
  expect(
    heights.some((height) => Math.abs(height - (streetHeight(null, [0, 0], true) + 0.004)) < 1e-6)
  ).toBe(true);
  expect(bridgeDeckHeight - bridgeDeckThickness).toBeGreaterThan(2.5);
});

test('병합 도로 면 선택은 빈 도로와 경계 면에서도 원본 도로를 유지', async () => {
  const { streetAtFace } = await import('./streetGeometryService');
  expect(streetAtFace([0, 2, 2, 7], 0)).toBe(1);
  expect(streetAtFace([0, 2, 2, 7], 1)).toBe(1);
  expect(streetAtFace([0, 2, 2, 7], 2)).toBe(3);
  expect(streetAtFace([0, 2, 2, 7], 6)).toBe(3);
  for (const face of [-1, 7, NaN, 0.1]) expect(streetAtFace([0, 2, 2, 7], face)).toBe(-1);
});
