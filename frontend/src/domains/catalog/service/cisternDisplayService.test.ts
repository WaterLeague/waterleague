import { expect, test } from 'vitest';
import { cisternDisplay } from './cisternDisplayService';

test('탱크는 원 건물 밖에 표시되고 같은 설치는 재접속 후 같은 위치와 크기로 복원', () => {
  const cell = {
    coordinates: [
      [0, 0],
      [20, 0],
      [20, 20],
      [0, 20],
    ] as [number, number][],
  };
  const small = cisternDisplay(cell, 100);
  const large = cisternDisplay(cell, 400);
  expect(small.center[0] - small.widthM / 2).toBeGreaterThan(20);
  expect(large.center[0] - large.widthM / 2).toBeGreaterThan(20);
  expect(large.widthM).toBe(2 * small.widthM);
  expect(large.capacityM3).toBe(4);
  expect(cisternDisplay(JSON.parse(JSON.stringify(cell)), 400)).toEqual(large);
});
