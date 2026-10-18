import { expect, test } from 'vitest';
import {
  designItems,
  historicalDesignDto,
  restoreDesign,
  type HistoricalDesign,
} from './designRepository';
const owner = '00000000-0000-4000-8000-000000000010';
const value = {
  eventId: 'seoul-20220808',
  revision: 7,
  snapshotSha256: 'a'.repeat(64),
  createdAt: '2026-10-19T00:00:00Z',
  snapshot: {
    schemaVersion: 1,
    eventId: 'seoul-20220808',
    elapsedSeconds: 3717,
    placements: [
      {
        item: {
          id: '00000000-0000-4000-8000-000000000001',
          districtId: '2419953',
          cellId: 'test-only',
          facilityType: 'GREEN_ROOF',
          areaM2: 20,
          installedAt: '2022-08-08T09:02:17Z',
        },
        site: {
          districtId: '2419953',
          cellId: 'test-only',
          allowedTypes: ['GREEN_ROOF'],
          center: [1, 2],
          heightM: 9.6,
        },
        cost: 5200000,
        rainfallModelHash: 'b'.repeat(64),
      },
    ],
  },
} as HistoricalDesign;
test('서버 저장본의 설치 시각·원화 비용·위치·시설 식별자를 그대로 복원', () => {
  const before = JSON.stringify(value),
    drafts = restoreDesign(value, owner);
  expect(drafts[0].marker).toMatchObject({
    id: value.snapshot!.placements[0].item.id,
    ownerId: owner,
    installedAt: '2022-08-08T09:02:17Z',
    cost: 5200000,
    center: [1, 2],
    heightM: 9.6,
  });
  expect(designItems(drafts)).toEqual([value.snapshot!.placements[0].item]);
  expect(JSON.stringify(value)).toBe(before);
});
test('빈 취소 저장본과 미작성 상태 구분 및 잘못된 사건·해시 상태 거부', () => {
  const empty = {
    eventId: 'seoul-20220808',
    revision: 0,
    snapshotSha256: null,
    createdAt: null,
    snapshot: null,
  };
  expect(historicalDesignDto.safeParse(empty).success).toBe(true);
  const cancelled = { ...value, snapshot: { ...value.snapshot!, placements: [] } };
  expect(historicalDesignDto.safeParse(cancelled).success).toBe(true);
  expect(restoreDesign(cancelled, owner)).toEqual([]);
  expect(historicalDesignDto.safeParse({ ...empty, revision: 1 }).success).toBe(false);
  expect(historicalDesignDto.safeParse({ ...cancelled, eventId: 'seoul-20110921' }).success).toBe(
    false
  );
});
test('다른 위치나 미허용 시설의 응답을 설치 마커로 복원하지 않음', () => {
  const row = value.snapshot!.placements[0];
  for (const site of [
    { ...row.site, cellId: 'other' },
    { ...row.site, allowedTypes: ['RAIN_GARDEN'] },
  ]) {
    const invalid = {
      ...value,
      snapshot: { ...value.snapshot!, placements: [{ ...row, site }] },
    } as HistoricalDesign;
    expect(() => restoreDesign(invalid, owner)).toThrow();
  }
});
