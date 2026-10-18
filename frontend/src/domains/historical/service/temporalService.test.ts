import { describe, expect, it } from 'vitest';
import {
  historicalScoreAt,
  matchesHistoricalDraft,
  scoreAt,
  temporalPolicy,
} from './temporalService';
import type { HistoricalDraft, HistoricalJob, HistoricalScoreFrame } from '../entity/historical';

const at = (second: number) => new Date(Date.UTC(2022, 7, 8, 9, 0, second)).toISOString();
const frame = (second: number, effect: number): HistoricalScoreFrame => ({
  at: at(second),
  differenceM3: effect,
  baselineAccountedM3: 5,
  designAccountedM3: 5 - effect,
});
describe('설치 시각 이후 재해 실험', () => {
  it('미래 프레임·최종 점수 누출 없이 뒤로 이동하며 음의 효과 보존', () => {
    const frames = [frame(37, 0), frame(60, -1), frame(120, 3)];
    expect(scoreAt(frames, at(36))).toBeNull();
    expect(scoreAt(frames, at(59))?.differenceM3).toBe(0);
    expect(scoreAt(frames, at(60))?.differenceM3).toBe(-1);
    expect(scoreAt(frames, at(120))?.differenceM3).toBe(3);
    expect(scoreAt(frames, at(61))?.differenceM3).toBe(-1);
  });
  it('서로 다른 설치 시각의 시설을 합산하며 자료 없는 결과는 0으로 만들지 않음', () => {
    const result = {
      temporalPolicy,
      facilities: [
        { cellId: 'a', installedAt: at(37), frames: [frame(37, 0), frame(60, -1), frame(120, 3)] },
        { cellId: 'b', installedAt: at(77), frames: [frame(77, 0), frame(120, 2)] },
      ],
    } as NonNullable<HistoricalJob['result']>;
    expect(historicalScoreAt(result, at(36))?.differenceM3).toBe(0);
    expect(historicalScoreAt(result, at(60))?.differenceM3).toBe(-1);
    expect(historicalScoreAt(result, at(80))?.differenceM3).toBe(-1);
    expect(historicalScoreAt(result, at(120))?.differenceM3).toBe(5);
    expect(historicalScoreAt({ ...result, temporalPolicy: undefined }, at(120))).toBeNull();
    expect(
      historicalScoreAt({ ...result, facilities: [{ cellId: 'a', installedAt: at(37) }] }, at(120))
    ).toBeNull();
  });
  it('설치 시간 변경·취소·이전 정책 결과를 현재 배치로 표시하지 않음', () => {
    const placement = {
      districtId: '2419953',
      cellId: 'a',
      facilityType: 'GREEN_ROOF',
      areaM2: 1,
      temporalPolicy,
      installedAt: at(37),
    };
    const job = { placements: [placement] } as HistoricalJob;
    const draft = {
      site: { districtId: '2419953', cellId: 'a' },
      facilityType: 'GREEN_ROOF',
      areaM2: 1,
      marker: { installedAt: at(37) },
    } as HistoricalDraft;
    expect(matchesHistoricalDraft(job, [draft])).toBe(true);
    expect(matchesHistoricalDraft(job, [])).toBe(false);
    expect(
      matchesHistoricalDraft(job, [{ ...draft, marker: { ...draft.marker, installedAt: at(38) } }])
    ).toBe(false);
    expect(
      matchesHistoricalDraft(
        {
          ...job,
          placements: [
            {
              ...placement,
              temporalPolicy: undefined,
              facilityType: 'GREEN_ROOF',
              siteModelHash: 'hash',
            },
          ],
        },
        [draft]
      )
    ).toBe(false);
  });
});
