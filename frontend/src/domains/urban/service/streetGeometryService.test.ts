import { expect, test } from 'vitest';

test('병합 도로 면 선택은 빈 도로와 경계 면에서도 원본 도로를 유지', async () => {
  const { streetAtFace } = await import('./streetGeometryService');
  expect(streetAtFace([0, 2, 2, 7], 0)).toBe(1);
  expect(streetAtFace([0, 2, 2, 7], 1)).toBe(1);
  expect(streetAtFace([0, 2, 2, 7], 2)).toBe(3);
  expect(streetAtFace([0, 2, 2, 7], 6)).toBe(3);
  for (const face of [-1, 7, NaN, 0.1]) expect(streetAtFace([0, 2, 2, 7], face)).toBe(-1);
});
