import { expect, it } from 'vitest';
import type { Placement } from '../entity/game';
import type { PlacementHistory } from '../entity/placementHistory';
import { placementHistoryReducer as reduce } from './placementHistoryService';

const empty = (): PlacementHistory => ({ past: [], present: [], future: [] });
const placement = (areaM2: number): Placement => ({
  cellId: 'G1',
  facilityType: 'RAIN_GARDEN',
  areaM2,
});

it('배치 추가·면적 변경·제거의 순서를 왕복 복원', () => {
  let state = empty();
  for (const placements of [[placement(10)], [placement(20)], []])
    state = reduce(state, { type: 'CHANGE', placements });
  for (const expected of [[placement(20)], [placement(10)], []]) {
    state = reduce(state, { type: 'UNDO' });
    expect(state.present).toEqual(expected);
  }
  expect(reduce(state, { type: 'UNDO' })).toBe(state);
  for (const expected of [[placement(10)], [placement(20)], []]) {
    state = reduce(state, { type: 'REDO' });
    expect(state.present).toEqual(expected);
  }
  expect(reduce(state, { type: 'REDO' })).toBe(state);
});

it('동일 배치 재적용은 다시 실행을 보존하고 새 수정은 이전 분기 폐기', () => {
  let state = reduce(empty(), { type: 'CHANGE', placements: [placement(10)] });
  state = reduce(state, { type: 'CHANGE', placements: [placement(20)] });
  state = reduce(state, { type: 'UNDO' });
  expect(reduce(state, { type: 'CHANGE', placements: [placement(10)] })).toBe(state);
  state = reduce(state, { type: 'CHANGE', placements: [placement(15)] });
  expect(state.future).toEqual([]);
  expect(reduce(state, { type: 'REDO' }).present).toEqual([placement(15)]);
});

it('최신 50개 변경만 보관하고 전체 왕복 후 현재 배치 유지', () => {
  let state = empty();
  for (let area = 1; area <= 55; area++)
    state = reduce(state, { type: 'CHANGE', placements: [placement(area)] });
  expect(state.past).toHaveLength(50);
  for (let i = 0; i < 60; i++) state = reduce(state, { type: 'UNDO' });
  expect(state.present).toEqual([placement(5)]);
  expect(state.future).toHaveLength(50);
  for (let i = 0; i < 60; i++) state = reduce(state, { type: 'REDO' });
  expect(state.present).toEqual([placement(55)]);
});

it('새 설계 초기화 직후 복사가 이전 설계를 이력에 넣지 않음', () => {
  let state = reduce(empty(), { type: 'CHANGE', placements: [placement(50)] });
  state = reduce(state, { type: 'RESET', placements: [] });
  state = reduce(state, { type: 'CHANGE', placements: [placement(30)] });
  state = reduce(state, { type: 'UNDO' });
  expect(state.present).toEqual([]);
  expect(state.past).toEqual([]);
  state = reduce(state, { type: 'RESET', placements: [placement(25)] });
  expect(state.future).toEqual([]);
  expect(reduce(state, { type: 'UNDO' }).present).toEqual([placement(25)]);
});

it('입력 참조 변조와 모델 전환으로 과거 배치가 섞이지 않음', () => {
  const input = [placement(10)];
  let state = reduce(empty(), { type: 'RESET', placements: input });
  input[0].areaM2 = 99;
  input.push({ ...placement(20), cellId: 'G2' });
  expect(state.present).toEqual([placement(10)]);
  state = reduce(state, { type: 'CHANGE', placements: input });
  input[0].areaM2 = 88;
  expect(state.present[0].areaM2).toBe(99);
  expect(state.past[0]).toEqual([placement(10)]);
  const current = state.present;
  state = reduce(state, { type: 'CLEAR_HISTORY' });
  expect(state).toEqual({ past: [], present: current, future: [] });
});
