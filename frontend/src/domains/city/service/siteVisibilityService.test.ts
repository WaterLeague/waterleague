import { expect, test } from 'vitest';
import {
  buildingOpacity,
  occupiedRoofSource,
  siteAppearance,
  availableSiteColor,
  selectedSiteColor,
} from './siteVisibilityService';
test('소속 구·후보·점유 구분의 불투명도', () => {
  expect(buildingOpacity(true, false)).toBe(1);
  expect(buildingOpacity(false, false)).toBe(0.2);
  expect(buildingOpacity(true, true)).toBe(0.16);
  expect(buildingOpacity(false, true)).toBe(0.07);
  expect(occupiedRoofSource('123', 'RW456', {})).toEqual(['way/456']);
  expect(occupiedRoofSource('123', 'R1', { '123:R1': ['way/789'] })).toEqual(['way/789']);
});

test('다른 시설 후보도 같은 색과 경계를 유지하며 불투명도만 감소', () => {
  const state = {
    eligible: true,
    matches: true,
    selected: false,
    installed: false,
    otherDistrict: false,
  };
  const normal = siteAppearance(state);
  const dimmed = siteAppearance({ ...state, matches: false });
  expect(normal.color).toBe(availableSiteColor);
  expect(dimmed.color).toBe(normal.color);
  expect(dimmed.fillOpacity).toBe(normal.fillOpacity);
  expect(dimmed.outlineOpacity).toBe(normal.outlineOpacity);
  expect(dimmed.opacity).toBeGreaterThan(0);
  expect(dimmed.opacity).toBeLessThan(normal.opacity);
});

test('선택 구역은 필터·점유·소속 구와 무관하게 노란색 강조 유지', () => {
  for (const matches of [true, false])
    for (const installed of [true, false])
      for (const otherDistrict of [true, false]) {
        const selected = siteAppearance({
          eligible: !installed,
          matches,
          selected: true,
          installed,
          otherDistrict,
        });
        expect(selected.color).toBe(selectedSiteColor);
        expect(selected.opacity).toBe(1);
        expect(selected.fillOpacity).toBeGreaterThan(0);
        expect(selected.outlineOpacity).toBe(1);
      }
});
