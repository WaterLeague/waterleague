import { expect, it } from 'vitest';
import {
  mapPatternAnalysis,
  mapResearchComparison,
  mapResearchComparisons,
} from './analysisMapper';
import { comparisonFingerprint, patternFingerprint } from '../service/analysisService';
const id = (n: number) => '10000000-0000-4000-8000-' + n.toString().padStart(12, '0');
const hash = (n: number) => n.toString().padStart(64, '0');
function pattern() {
  return {
    modelHash: hash(1),
    method: 'SELECTED_UNIQUE_INPUT_TOP_K_WITH_TIES_V1',
    requestedCount: 4,
    uniqueInputCount: 3,
    duplicateInputCount: 1,
    topK: 2,
    includedCount: 3,
    cutoffScore: -2,
    designs: [1, 2, 3].map((n) => ({
      jobId: id(n),
      inputHash: hash(n),
      score: n === 1 ? 1 : -2,
      costKrw: n * 100,
    })),
    placements: [
      {
        cellId: 'G1',
        facilityType: 'RAIN_GARDEN',
        designCount: 2,
        frequencyPercent: 66.67,
        minimumAreaM2: 10,
        maximumAreaM2: 20,
        meanInstalledAreaM2: 15,
        meanAllDesignAreaM2: 10,
      },
    ],
    facilityPairs: [
      { first: 'GREEN_ROOF', second: 'PERMEABLE_PAVEMENT', designCount: 0, frequencyPercent: 0 },
      { first: 'GREEN_ROOF', second: 'RAIN_GARDEN', designCount: 1, frequencyPercent: 33.33 },
      { first: 'PERMEABLE_PAVEMENT', second: 'RAIN_GARDEN', designCount: 0, frequencyPercent: 0 },
    ],
    minimumCostKrw: 100,
    maximumCostKrw: 300,
    minimumScore: -2,
    maximumScore: 1,
    limitations: ['테스트용 기술 통계'],
  };
}
it('동점 포함·물리 입력 중복 제거·음수 점수와 올바른 면적 분모 수용', () => {
  expect(mapPatternAnalysis(pattern()).includedCount).toBe(3);
});
it('표본 수·동점 경계·입력 중복·면적 분모·빈도 불일치 거부', () => {
  const mutations = [
    (d: ReturnType<typeof pattern>) => {
      d.duplicateInputCount = 0;
    },
    (d: ReturnType<typeof pattern>) => {
      d.includedCount = 2;
    },
    (d: ReturnType<typeof pattern>) => {
      d.cutoffScore = 0;
    },
    (d: ReturnType<typeof pattern>) => {
      d.designs[1].inputHash = d.designs[0].inputHash;
    },
    (d: ReturnType<typeof pattern>) => {
      d.placements[0].frequencyPercent = 50;
    },
    (d: ReturnType<typeof pattern>) => {
      d.placements[0].meanAllDesignAreaM2 = 15;
    },
    (d: ReturnType<typeof pattern>) => {
      d.placements.push(d.placements[0]);
    },
    (d: ReturnType<typeof pattern>) => {
      d.facilityPairs[0] = d.facilityPairs[1];
    },
  ];
  for (const change of mutations) {
    const d = pattern();
    change(d);
    expect(() => mapPatternAnalysis(d)).toThrow();
  }
});
function comparison() {
  const time = '2026-10-16T00:00:00Z';
  const metrics = {
    runoffM3: 1,
    surfaceRunoffM3: 1,
    lidDrainageM3: 0,
    finalStorageM3: 0,
    initialStorageM3: 0,
    accountedDischargeM3: 1,
    infiltrationM3: 0,
    evaporationM3: 0,
    precipitationM3: 1,
    runoffContinuityPercent: 0,
    peakM3s: 0.1,
    seriesM3s: [0.1],
  };
  const result = {
    score: 0,
    official: false,
    validationLevel: 'EXPLORATORY',
    baseline: metrics,
    strategy: metrics,
    assumptions: [],
    sensitivity: [],
    engine: { version: 'test', binarySha256: hash(9), generatorSha256: hash(8), platform: 'test' },
  };
  return {
    id: id(1),
    organizationId: id(2),
    sourceJobId: id(3),
    requestHash: hash(1),
    createdAt: time,
    sourceSimulation: {
      id: id(3),
      versionId: id(4),
      state: 'SUCCEEDED',
      modelHash: hash(1),
      inputHash: hash(2),
      result,
      errorCode: null,
      createdAt: time,
    },
    comparison: {
      id: id(5),
      title: '시험',
      sourceVersionId: id(4),
      createdAt: time,
      sourceVersion: {
        id: id(4),
        strategyId: id(6),
        revision: 1,
        modelHash: hash(1),
        inputHash: hash(2),
        placements: [],
        designNote: '',
        cost: 0,
        currency: 'KRW',
        createdAt: time,
        events: { kind: 'SERVER_SNAPSHOT_CHANGE', before: [], after: [] },
      },
      jobs: [10, 11].map((n) => ({
        id: id(n),
        versionId: id(n + 10),
        strategyId: id(n + 20),
        state: 'QUEUED',
        modelHash: hash(n),
        inputHash: hash(n + 10),
        result: null,
        errorCode: null,
        createdAt: time,
      })),
    },
  };
}
it('기관 비교 원본 계산·버전·모델·입력 연결과 파생 결과 상태 검사', () => {
  expect(mapResearchComparison(comparison()).comparison.jobs).toHaveLength(2);
  for (const field of ['id', 'versionId', 'modelHash', 'inputHash', 'state'] as const) {
    const d = comparison();
    d.sourceSimulation[field] = field.endsWith('Hash')
      ? hash(99)
      : field === 'state'
        ? 'QUEUED'
        : id(99);
    expect(() => mapResearchComparison(d)).toThrow();
  }
  const d = comparison();
  d.comparison.jobs[0].state = 'SUCCEEDED';
  expect(() => mapResearchComparison(d)).toThrow();
  const row = { id: id(1), sourceJobId: id(3), title: '시험', createdAt: d.createdAt };
  expect(() => mapResearchComparisons([row, row])).toThrow();
});
it('선택 순서만 다른 재전송은 같은 요청이며 원본·표본·상위 기준 변경은 구분', () => {
  expect(comparisonFingerprint(id(1), [hash(1), hash(2)])).toBe(
    comparisonFingerprint(id(1), [hash(2), hash(1)])
  );
  expect(comparisonFingerprint(id(1), [hash(1), hash(2)])).not.toBe(
    comparisonFingerprint(id(2), [hash(1), hash(2)])
  );
  expect(patternFingerprint([id(1), id(2)], 2)).toBe(patternFingerprint([id(2), id(1)], 2));
  expect(patternFingerprint([id(1), id(2)], 2)).not.toBe(patternFingerprint([id(1), id(2)], 1));
});
