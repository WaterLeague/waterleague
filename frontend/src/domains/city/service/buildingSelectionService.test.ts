import { expect, test } from 'vitest';
import { buildingFaceIndex } from './buildingSelectionService';
test('병합 메시의 시작·경계·마지막 면에서 원본 건물 선택', () => {
  expect([0, 11, 12, 35, 36, 41, 42].map((f) => buildingFaceIndex([12, 36, 42], f))).toEqual([
    0, 0, 1, 1, 2, 2, -1,
  ]);
  expect(buildingFaceIndex([], 0)).toBe(-1);
  expect(buildingFaceIndex([12], -1)).toBe(-1);
});
