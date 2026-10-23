import { describe, expect, it } from 'vitest';
import { districtScoreLabel } from './districtScoreLabel';
import type { WeeklySnapshot } from '../dto/weeklyDto';

describe('지도 구별 점수 상태', () => {
  const district: WeeklySnapshot['current']['districts'][number] = {
    districtId: '11320',
    districtName: '도봉구',
    rank: null,
    scoreM3: null,
    evaluatedSeconds: 60,
    expectedSeconds: 120,
    evaluatedMinutes: 1,
    expectedMinutes: 2,
    scoreM3Exact: null,
  };
  it('계산 기록이 있으나 조건이 섞인 합계를 0이나 점수 없음으로 표시하지 않음', () => {
    expect(districtScoreLabel(district, true)).toBe('합산 보류');
    expect(districtScoreLabel(district, true, false)).toBe('합산 보류');
  });
  it('계산 기록이 없는 구는 점수 없음 유지', () => {
    expect(districtScoreLabel({ ...district, evaluatedSeconds: 0 }, true)).toBe('점수 없음');
  });
  it('실제 계산된 0은 숫자로 유지', () => {
    expect(districtScoreLabel({ ...district, scoreM3: 0, scoreM3Exact: '0', rank: 6 }, false)).toBe(
      '6위 · 총 점수 0 m³'
    );
  });
});
