import { describe, expect, it } from 'vitest';
import { isPareto } from './paretoService';
import type { ResearchEntry } from '../entity/research';

const entry = (cost: number, score: number): ResearchEntry => ({
  jobId: `${cost}:${score}`,
  cost,
  score,
  designNote: '',
  revision: 1,
  submittedAt: '',
});

describe('비용·성능 비교', () => {
  it('동률과 비용·성능 절충안을 유지하고 같은 비용의 열위 기록을 제외', () => {
    const values = [entry(0, 0), entry(10, 5), entry(10, 5), entry(20, 8), entry(20, 6)];
    expect(values.map((value) => isPareto(value, values))).toEqual([true, true, true, true, false]);
  });
  it('기준안보다 악화된 음수 점수를 유리한 후보로 분류하지 않음', () => {
    const values = [entry(0, 0), entry(10, -2)];
    expect(isPareto(values[1], values)).toBe(false);
  });
});
