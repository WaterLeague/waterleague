import type { HistoricalState } from '../controller/useHistorical';

export function historicalTotal(
  state: Pick<HistoricalState, 'facilityStates' | 'design' | 'duration' | 'elapsedSeconds'>,
  authenticated: boolean
) {
  const active = state.facilityStates.filter((f) => !f.before);
  const locked = !authenticated && state.duration > 0 && state.elapsedSeconds >= state.duration;
  // 다른 구의 시설도 합산하되 결측 점수나 미래 설치를 0점으로 대체하지 않는다.
  const score =
    !state.design.ready || locked || active.some((f) => !f.score)
      ? null
      : active.reduce((sum, f) => sum + f.score!.differenceM3, 0);
  return { count: state.design.ready ? active.length : null, score, locked };
}
