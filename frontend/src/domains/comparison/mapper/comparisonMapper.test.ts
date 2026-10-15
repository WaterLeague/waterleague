import { expect, it } from 'vitest';
import { mapComparison } from './comparisonMapper';
import { comparisonState } from '../service/comparisonService';
import type { Job } from '../../game/entity/game';
const uid = (n: number) => '10000000-0000-4000-8000-' + n.toString().padStart(12, '0');
const hash = (n: number) => n.toString().padStart(64, '0');
function fixture() {
  const jobs: (Job & { strategyId: string })[] = [1, 2].map((n) => ({
    id: uid(n),
    versionId: uid(n + 10),
    strategyId: uid(n + 20),
    state: 'QUEUED',
    modelHash: hash(n),
    inputHash: hash(n + 10),
    result: null,
    errorCode: null,
    createdAt: '2026-10-16T00:00:00Z',
  }));
  return {
    id: uid(30),
    title: '비교 시험',
    sourceVersionId: uid(31),
    createdAt: '2026-10-16T00:00:00Z',
    sourceVersion: {
      id: uid(31),
      strategyId: uid(32),
      revision: 1,
      modelHash: hash(3),
      inputHash: hash(13),
      placements: [],
      designNote: '',
      cost: 0,
      currency: 'KRW',
      createdAt: '2026-10-16T00:00:00Z',
      events: { kind: 'SERVER_SNAPSHOT_CHANGE', before: [], after: [] },
    },
    jobs,
  };
}
it('원본 버전 불일치·중복 강우·결과 없는 성공 상태 거부', () => {
  expect(mapComparison(fixture()).jobs).toHaveLength(2);
  const a = fixture();
  a.sourceVersionId = uid(99);
  expect(() => mapComparison(a)).toThrow();
  const b = fixture();
  b.jobs[1].modelHash = b.jobs[0].modelHash;
  expect(() => mapComparison(b)).toThrow();
  const c = fixture();
  c.jobs[0].state = 'SUCCEEDED';
  expect(() => mapComparison(c)).toThrow();
});
it('실패가 있는 비교를 전체 성공으로 표시하지 않음', () => {
  const data = fixture();
  data.jobs[0].state = 'FAILED';
  data.jobs[0].errorCode = 'ENGINE_FAILED';
  expect(comparisonState(mapComparison(data))).toBe('계산 진행 중');
  data.jobs[1].state = 'REJECTED';
  expect(comparisonState(mapComparison(data))).toBe('일부 계산 실패');
});
