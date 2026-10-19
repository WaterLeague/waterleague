import { expect, test } from 'vitest';
import {
  candidateMask,
  candidateMatches,
  candidateBounds,
  type GroundCandidate,
} from './candidateTilesService';
test('기본 후보와 시설 선택·해제의 전체/호환 유형 표시', () => {
  const parking: GroundCandidate = ['G1', '1', 43, [0, 0, 1, 0, 1, 1, 0, 0]],
    road: GroundCandidate = ['S1', '1', 2, [2, 0, 3, 0, 3, 1, 2, 0]];
  expect(candidateMatches(parking, '')).toBe(true);
  expect(candidateMatches(road, '')).toBe(true);
  expect(candidateMatches(parking, 'RAIN_GARDEN')).toBe(true);
  expect(candidateMatches(road, 'RAIN_GARDEN')).toBe(false);
  expect(candidateMatches(road, 'PERMEABLE_PAVEMENT')).toBe(true);
  expect(candidateMatches(parking, 'GREEN_ROOF')).toBe(false);
  expect(candidateMask('')).toBe(0);
  expect(candidateBounds([500, 500], 100)).toEqual([200, 200, 800, 800]);
});
