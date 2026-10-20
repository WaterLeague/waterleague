import { expect, test, vi } from 'vitest';
import { runHistorical } from './historicalRepository';
import type { HistoricalDraft } from '../entity/historical';

const request = vi.hoisted(() => vi.fn().mockResolvedValue({ state: 'QUEUED' }));
vi.mock('../../../shared/repository/apiClient', () => ({ api: request }));

test('막힘 비교 대상은 기존 설계·설치 시각과 별도로 요청에 결속', async () => {
  const cellId = 'C' + 'a'.repeat(24);
  const draft = {
    site: { cellId, districtId: '11200', modelHash: 'b'.repeat(64) },
    facilityType: 'PERMEABLE_PAVEMENT',
    areaM2: 10,
    marker: { installedAt: '2022-08-08T00:00:37Z' },
  } as HistoricalDraft;
  const before = structuredClone(draft);
  await runHistorical(
    '11200',
    'c'.repeat(64),
    [draft],
    'request',
    undefined,
    undefined,
    { revision: 2, eventId: 'seoul-20220808' },
    cellId
  );
  const [path, method, body] = request.mock.calls.at(-1)!;
  expect(path).toBe('/historical');
  expect(method).toBe('POST');
  expect(body.pavementComparisonCellId).toBe(cellId);
  expect(body).not.toHaveProperty('sensitivityCellId');
  expect(body.placements[0]).toMatchObject({
    cellId,
    facilityType: 'PERMEABLE_PAVEMENT',
    areaM2: 10,
    installedAt: draft.marker.installedAt,
  });
  expect(draft).toEqual(before);
  await runHistorical('11200', 'c'.repeat(64), [draft], 'ordinary');
  expect(request.mock.calls.at(-1)![2]).not.toHaveProperty('pavementComparisonCellId');
});
