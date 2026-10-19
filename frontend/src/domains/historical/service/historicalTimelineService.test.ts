import { expect, test } from 'vitest';
import type { HistoricalDraft } from '../entity/historical';
import { installationTimelineGroups } from './historicalTimelineService';
const start = '2022-08-08T09:00:00Z';
const draft = (id: string, seconds: number) =>
  ({
    marker: { id, installedAt: new Date(Date.parse(start) + seconds * 1000).toISOString() },
  }) as HistoricalDraft;

test('설치 초 단위 위치와 양 끝 경계, 잘못된 사건 시각 제외', () => {
  const drafts = [
    draft('end', 3600),
    draft('early', 4),
    draft('middle', 1800),
    draft('outside', 3601),
  ];
  const before = JSON.stringify(drafts);
  const groups = installationTimelineGroups(drafts, start, 3600, 500);
  expect(groups.map((g) => g.id)).toEqual(['early', 'middle', 'end']);
  expect(groups.map((g) => g.position)).toEqual([4 / 3600, 0.5, 1]);
  expect(JSON.stringify(drafts)).toBe(before);
  expect(installationTimelineGroups(drafts, undefined, 3600, 500)).toEqual([]);
  expect(installationTimelineGroups(drafts, start, 0, 500)).toEqual([]);
});

test('좁은 화면·동일 시각의 설치를 묶어도 개별 시각·선택 항목 보존', () => {
  const drafts = [draft('a', 4), draft('b', 4), draft('c', 1000), draft('d', 3600)];
  const small = installationTimelineGroups(drafts, start, 3600, 100);
  expect(small).toHaveLength(2);
  expect(small[0].events.map((e) => e.seconds)).toEqual([4, 4, 1000]);
  expect(installationTimelineGroups(drafts, start, 3600, 1000)).toHaveLength(3);
});
