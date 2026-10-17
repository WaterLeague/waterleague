import { expect, test } from 'vitest';
import { buildingOpacity, occupiedRoofSource } from './siteVisibilityService';
test('소속 구·후보·점유 구분의 불투명도', () => {
  expect(buildingOpacity(true, false)).toBe(1);
  expect(buildingOpacity(false, false)).toBe(0.2);
  expect(buildingOpacity(true, true)).toBe(0.16);
  expect(buildingOpacity(false, true)).toBe(0.07);
  expect(occupiedRoofSource('123', 'RW456', {})).toEqual(['way/456']);
  expect(occupiedRoofSource('123', 'R1', { '123:R1': ['way/789'] })).toEqual(['way/789']);
});
