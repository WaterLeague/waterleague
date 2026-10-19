import { expect, test } from 'vitest';
import type { HistoricalDraft, HistoricalJob } from '../entity/historical';
import {
  historicalFacilityStates,
  nextHistoricalCalculation,
  temporalPolicy,
} from './temporalService';
const regions = [
  { districtId: '2410520', modelHash: 'a' },
  { districtId: '2419953', modelHash: 'b' },
];
const at = (second: number) => new Date(Date.UTC(2022, 7, 8, 9, 0, second)).toISOString();
const drafts = regions.map((r, i) => ({
  site: { districtId: r.districtId, cellId: 'same-local-id', modelHash: 'site-' + i },
  facilityType: 'GREEN_ROOF',
  areaM2: 20,
  marker: { id: String(i), installedAt: at(i ? 137 : 37) },
})) as HistoricalDraft[];
const job = (i: number, state: HistoricalJob['state'] = 'SUCCEEDED') =>
  ({
    id: 'job-' + i,
    modelHash: regions[i].modelHash,
    districtId: regions[i].districtId,
    state,
    placements: [
      {
        districtId: regions[i].districtId,
        cellId: drafts[i].site.cellId,
        siteModelHash: drafts[i].site.modelHash,
        areaM2: 20,
        facilityType: 'GREEN_ROOF',
        temporalPolicy,
        installedAt: drafts[i].marker.installedAt,
      },
    ],
    result:
      state === 'SUCCEEDED'
        ? {
            temporalPolicy,
            facilities: [
              {
                cellId: drafts[i].site.cellId,
                installedAt: drafts[i].marker.installedAt,
                frames: [
                  { at: drafts[i].marker.installedAt, differenceM3: 0 },
                  { at: at(180), differenceM3: i ? 2 : -1 },
                ],
              },
            ],
          }
        : null,
  }) as HistoricalJob;

test('카메라 선택 구와 무관하게 전체 설계를 순차 계산하고 실행 중 중복 요청 방지', () => {
  const attempts = new Map<string, string>();
  const first = nextHistoricalCalculation(regions, drafts, {}, attempts)!;
  expect(first.districtId).toBe(regions[0].districtId);
  expect(nextHistoricalCalculation(regions, drafts, { a: job(0, 'RUNNING') }, attempts)).toBeNull();
  expect(nextHistoricalCalculation(regions, drafts, { a: job(0) }, attempts)?.districtId).toBe(
    regions[1].districtId
  );
  expect(nextHistoricalCalculation(regions, drafts, { a: job(0), b: job(1) }, attempts)).toBeNull();
});
test('한 구 실패나 요청 유실이 다른 구 계산을 막거나 자동 재시도 폭주를 만들지 않음', () => {
  const first = nextHistoricalCalculation(regions, drafts, {}, new Map())!;
  const attempts = new Map([[first.districtId, first.signature]]);
  expect(nextHistoricalCalculation(regions, drafts, {}, attempts)?.districtId).toBe(
    regions[1].districtId
  );
  expect(
    nextHistoricalCalculation(regions, drafts, { a: job(0, 'FAILED') }, new Map())?.districtId
  ).toBe(regions[1].districtId);
  const changed = [{ ...drafts[0], areaM2: 25 }, drafts[1]];
  expect(nextHistoricalCalculation(regions, changed, { a: job(0) }, attempts)?.districtId).toBe(
    regions[0].districtId
  );
  expect(nextHistoricalCalculation(regions, [], {}, attempts)).toBeNull();
});
test('구별 같은 시설 ID 분리·설치 이전 제외·음의 효과·실패와 결측 보존', () => {
  const jobs = { a: job(0), b: job(1) };
  const early = historicalFacilityStates(regions, drafts, jobs, at(100));
  expect(early.map((v) => v.before)).toEqual([false, true]);
  expect(early.map((v) => v.score?.differenceM3 ?? null)).toEqual([0, null]);
  expect(
    historicalFacilityStates(regions, drafts, jobs, at(180)).map((v) => v.score?.differenceM3)
  ).toEqual([-1, 2]);
  const failed = historicalFacilityStates(
    regions,
    drafts,
    { ...jobs, b: job(1, 'FAILED') },
    at(180)
  );
  expect(failed[1].score).toBeNull();
  expect(failed[1].state).toBe('FAILED');
  expect(
    historicalFacilityStates(regions, [{ ...drafts[0], areaM2: 25 }], jobs, at(180))[0].score
  ).toBeNull();
});
