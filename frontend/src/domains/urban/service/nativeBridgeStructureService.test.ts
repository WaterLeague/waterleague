import { expect, test } from 'vitest';
import { bridgePierPositions } from './nativeBridgeStructureService';
import { inBuildingRing } from '../../city/service/buildingSelectionService';
test('한강을 비스듬히 건너는 긴 상판에서도 교각이 전 구간 내부에 분포', () => {
  const ring: [number, number][] = [
    [0, 0],
    [1000, 1000],
    [990, 1010],
    [-10, 10],
    [0, 0],
  ];
  const points = bridgePierPositions([[ring]]);
  expect(points.length).toBeGreaterThan(20);
  expect(points.every((p) => inBuildingRing(p, ring))).toBe(true);
  expect(Math.min(...points.map((p) => p[0]))).toBeLessThan(50);
  expect(Math.max(...points.map((p) => p[0]))).toBeGreaterThan(925);
});
test('교각은 상판의 구멍과 원형 사이 빈 곳을 침범하지 않음', () => {
  const outer: [number, number][] = [
    [0, 0],
    [300, 0],
    [300, 30],
    [0, 30],
    [0, 0],
  ];
  const hole: [number, number][] = [
    [30, 5],
    [270, 5],
    [270, 25],
    [30, 25],
    [30, 5],
  ];
  const points = bridgePierPositions([[outer, hole]]);
  expect(points.length).toBeGreaterThan(0);
  expect(points.every((p) => inBuildingRing(p, outer) && !inBuildingRing(p, hole))).toBe(true);
});
