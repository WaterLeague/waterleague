import { expect, it } from 'vitest';
import { historicalTotal } from './historicalTotal';
import type { HistoricalState } from '../controller/useHistorical';
const state = () =>
  ({
    design: { ready: true },
    duration: 600,
    elapsedSeconds: 180,
    facilityStates: [
      { before: false, draft: { site: { districtId: 'a' } }, score: { differenceM3: 2 } },
      { before: false, draft: { site: { districtId: 'b' } }, score: { differenceM3: -0.5 } },
      { before: true, draft: { site: { districtId: 'c' } }, score: null },
    ],
  }) as HistoricalState;
it('여러 구의 설치 점수 합산, 음수 유지, 미래 시설 제외', () => {
  expect(historicalTotal(state(), false)).toEqual({ count: 2, score: 1.5, locked: false });
});
it('일부 미계산·설계 미복원을 0점으로 표시하지 않음', () => {
  const s = state();
  s.facilityStates[0].score = null;
  expect(historicalTotal(s, true).score).toBeNull();
  s.design.ready = false;
  expect(historicalTotal(s, true).count).toBeNull();
});
it('게스트의 최종 점수는 잠그고 회원 최종 점수와 빈 설계의 0점 유지', () => {
  const s = state();
  s.elapsedSeconds = s.duration;
  expect(historicalTotal(s, false)).toEqual({ count: 2, score: null, locked: true });
  expect(historicalTotal(s, true).score).toBe(1.5);
  s.facilityStates = [];
  expect(historicalTotal(s, true).score).toBe(0);
});
