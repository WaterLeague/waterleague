import { expect, test } from 'vitest';
import { Color } from 'three';
import { structureWriter } from './structureGeometryService';

test('상판 경계의 난간 양옆 모서리가 중심선 높이를 공유', () => {
  const positions: number[] = [],
    colors: number[] = [];
  const writer = structureWriter(positions, colors, null, (p) => (p[1] >= 0 ? 12 : 0));
  writer.beam([0, 0], [20, 0], 0.5, 0.1, 0.08, new Color('white'));
  const heights = positions.filter((_, i) => i % 3 === 1);
  expect(Math.min(...heights)).toBe(12.5);
  expect(Math.max(...heights)).toBe(12.6);
});
