import { expect, it } from 'vitest';
import generation from '../../../../../simulation/tests/fixtures/pattern-search-v1.json';
import model from '../../../../../data/models/seongsu-lab.json';
import { mapLab } from '../../game/mapper/labMapper';
import { mapSearch, mapSearches } from './searchMapper';
import { searchFingerprint, searchInputError, searchState } from '../service/searchService';
export const uuid = (n: number) => '10000000-0000-4000-8000-' + n.toString().padStart(12, '0');
export const lab = mapLab({ modelHash: generation.modelHash, model });
export function queued() {
  const g = structuredClone(generation);
  for (const source of g.sources) {
    source.sample.jobId = uuid(Number(source.sample.jobId.slice(-12)));
    source.sample.versionId = uuid(Number(source.sample.versionId.slice(-12)));
  }
  return {
    id: uuid(1000),
    organizationId: uuid(1001),
    requestHash: 'a'.repeat(64),
    modelHash: g.modelHash,
    provenanceHash: 'b'.repeat(64),
    createdAt: '2026-10-17T00:00:00Z',
    validationLevel: 'EXPLORATORY',
    official: false,
    generation: g,
    sourceBestScore: Math.max(...g.sources.map((s) => s.sample.score)),
    completeComparison: false,
    arms: ['PATTERN', 'UNIFORM'].map((arm) => ({
      arm,
      total: 4,
      queued: 4,
      running: 0,
      succeeded: 0,
      failed: 0,
      rejected: 0,
      bestScore: null as number | null,
    })),
    candidates: g.candidates.map((c, i) => ({
      ...c,
      id: uuid(2000 + i),
      modelHash: g.modelHash,
      state: 'QUEUED',
      result: null as unknown,
      score: null as number | null,
      errorCode: null as string | null,
      createdAt: '2026-10-17T00:00:00Z',
      finishedAt: null as string | null,
    })),
  };
}
function completed() {
  const d = queued();
  const metrics = {
    runoffM3: 90,
    surfaceRunoffM3: 90,
    lidDrainageM3: 0,
    finalStorageM3: 0,
    initialStorageM3: 0,
    accountedDischargeM3: 90,
    infiltrationM3: 10,
    evaporationM3: 0,
    precipitationM3: 100,
    runoffContinuityPercent: 0,
    peakM3s: 1,
    seriesM3s: Array(lab.model.rainfall.depthsMm.length).fill(0),
  };
  for (const c of d.candidates) {
    c.state = 'SUCCEEDED';
    c.score = 10;
    c.finishedAt = d.createdAt;
    c.result = {
      score: 10,
      modelHash: c.modelHash,
      inputHash: c.inputHash,
      official: false,
      validationLevel: 'EXPLORATORY',
      baseline: { ...metrics, accountedDischargeM3: 100 },
      strategy: metrics,
      assumptions: [],
      sensitivity: [],
      engine: {
        version: 'TEST_ONLY',
        binarySha256: 'c'.repeat(64),
        generatorSha256: 'd'.repeat(64),
        platform: 'TEST_ONLY',
      },
    };
  }
  d.completeComparison = true;
  d.arms = d.arms.map((a) => ({ ...a, queued: 0, succeeded: 4, bestScore: 10 }));
  return d;
}
it('Java 생성 계보의 고유/학습 표본과 두 방법의 후보·원화 비용 수용', () => {
  const d = queued(),
    mapped = mapSearch(d, lab, uuid(1001), {
      jobIds: d.generation.sources.map((s) => s.sample.jobId),
      settings: d.generation.settings,
    });
  expect(mapped.candidates).toHaveLength(8);
  expect(mapped.generation.trainingCount).toBe(3);
  expect(searchState(mapped)).toContain('8개');
  expect(mapSearch(completed(), lab, uuid(1001)).completeComparison).toBe(true);
});
it('다른 기관/모델/요청과 원본 집합·배치·비용·학습 범위 불일치 거부', () => {
  expect(() => mapSearch(queued(), lab, uuid(99))).toThrow();
  expect(() => mapSearch(queued(), { ...lab, modelHash: 'f'.repeat(64) }, uuid(1001))).toThrow();
  expect(() =>
    mapSearch(queued(), lab, uuid(1001), {
      jobIds: [uuid(1), uuid(2)],
      settings: generation.settings,
    })
  ).toThrow();
  const changes = [
    (d: ReturnType<typeof queued>) => {
      d.generation.requestedCount++;
    },
    (d: ReturnType<typeof queued>) => {
      d.generation.sources[0].selected = false;
    },
    (d: ReturnType<typeof queued>) => {
      d.generation.sources[0].sample.costKrw++;
    },
    (d: ReturnType<typeof queued>) => {
      d.candidates[0].placements[0].areaM2++;
    },
    (d: ReturnType<typeof queued>) => {
      d.candidates[0].costKrw++;
    },
    (d: ReturnType<typeof queued>) => {
      d.candidates[1].ordinal = d.candidates[0].ordinal;
    },
    (d: ReturnType<typeof queued>) => {
      d.generation.sharedCandidateCount++;
    },
    (d: ReturnType<typeof queued>) => {
      d.generation.distributions[0].options[0].patternWeight++;
    },
  ];
  for (const change of changes) {
    const d = queued();
    change(d);
    expect(() => mapSearch(d, lab, uuid(1001))).toThrow();
  }
});
it('불완전 비교·최고점·후보 상태·물수지 점수·결과 식별값 변조 거부', () => {
  const mutations = [
    (d: ReturnType<typeof completed>) => {
      d.completeComparison = false;
    },
    (d: ReturnType<typeof completed>) => {
      d.arms[0].bestScore = 90;
    },
    (d: ReturnType<typeof completed>) => {
      d.candidates[0].score = 90;
    },
    (d: ReturnType<typeof completed>) => {
      d.candidates[0].state = 'RUNNING';
    },
    (d: ReturnType<typeof completed>) => {
      (d.candidates[0].result as { inputHash: string }).inputHash = 'f'.repeat(64);
    },
  ];
  for (const change of mutations) {
    const d = completed();
    change(d);
    expect(() => mapSearch(d, lab, uuid(1001))).toThrow();
  }
  const d = queued();
  d.candidates[0].state = 'FAILED';
  d.candidates[0].errorCode = 'SIMULATION_TIMEOUT';
  d.arms[0].queued--;
  d.arms[0].failed++;
  expect(mapSearch(d, lab, uuid(1001)).completeComparison).toBe(false);
});
it('현재 모델 기록 필터와 집계/중복 검증, 요청 재전송 키와 입력 범위 구분', () => {
  const d = queued(),
    row = { ...d, settings: d.generation.settings };
  expect(mapSearches([row], lab.modelHash)).toHaveLength(1);
  expect(mapSearches([row], 'f'.repeat(64))).toEqual([]);
  expect(() => mapSearches([row, row], lab.modelHash)).toThrow();
  const a = { jobIds: [uuid(1), uuid(2)], settings: { ...generation.settings } };
  expect(searchFingerprint(a)).toBe(searchFingerprint({ ...a, jobIds: [...a.jobIds].reverse() }));
  expect(searchInputError(a, lab.model.budget, [100, 200])).toBe('');
  expect(
    searchInputError({ ...a, settings: { ...a.settings, budgetKrw: 1.2 } }, lab.model.budget, [])
  ).toContain('정수');
  expect(
    searchInputError({ ...a, settings: { ...a.settings, budgetKrw: 100 } }, lab.model.budget, [200])
  ).toContain('원본');
});
