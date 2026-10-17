import { expect, it } from 'vitest';
import type { Job, Placement, Version } from '../entity/game';
import { matchesEvaluatedDesign } from './roundService';
const placements: Placement[] = [
  { cellId: 'G1', facilityType: 'RAIN_GARDEN', areaM2: 40 },
  { cellId: 'R1', facilityType: 'GREEN_ROOF', areaM2: 20 },
];
const version: Version = {
  id: 'version-1',
  strategyId: 'strategy-1',
  revision: 1,
  modelHash: 'model-1',
  inputHash: 'input-1',
  placements,
  designNote: '',
  cost: 100,
  currency: 'KRW',
  createdAt: '2026-10-17T00:00:00Z',
  events: { kind: 'CREATE', before: [], after: placements },
};
const job: Job = {
  id: 'job-1',
  versionId: version.id,
  state: 'SUCCEEDED',
  result: null,
  errorCode: null,
  createdAt: version.createdAt,
  modelHash: version.modelHash,
  inputHash: version.inputHash,
};
it('배열 순서·메모와 무관하게 계산한 물리 배치 일치 판정', () => {
  expect(
    matchesEvaluatedDesign(
      job,
      { ...version, designNote: '메모 변경' },
      'model-1',
      [...placements].reverse()
    )
  ).toBe(true);
});
it('계산 후 면적·종류·구역·개수 변경과 중복 구역을 이전 결과로 판정', () => {
  const changes: Placement[][] = [
    [],
    [placements[0]],
    [placements[0], placements[0]],
    [{ ...placements[0], areaM2: 41 }, placements[1]],
    [{ ...placements[0], facilityType: 'PERMEABLE_PAVEMENT' }, placements[1]],
    [{ ...placements[0], cellId: 'G2' }, placements[1]],
  ];
  for (const changed of changes)
    expect(matchesEvaluatedDesign(job, version, 'model-1', changed)).toBe(false);
  expect(matchesEvaluatedDesign(job, version, 'model-1', placements)).toBe(true);
});
it('모델 전환·저장 버전 교체·입력 해시 불일치·실행 누락 거부', () => {
  expect(matchesEvaluatedDesign(job, version, 'model-2', placements)).toBe(false);
  expect(matchesEvaluatedDesign(job, { ...version, id: 'version-2' }, 'model-1', placements)).toBe(
    false
  );
  expect(
    matchesEvaluatedDesign(job, { ...version, inputHash: 'input-2' }, 'model-1', placements)
  ).toBe(false);
  expect(matchesEvaluatedDesign(null, version, 'model-1', placements)).toBe(false);
  expect(matchesEvaluatedDesign(job, null, 'model-1', placements)).toBe(false);
});
