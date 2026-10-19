import { describe, expect, it, vi } from 'vitest';
import type { HistoricalDraft, HistoricalJob } from '../entity/historical';
import {
  submissionPlacements,
  submitHistorical,
  submitSavedHistorical,
} from './submissionRepository';
import { api } from '../../../shared/repository/apiClient';
vi.mock('../../../shared/repository/apiClient', () => ({ api: vi.fn() }));

describe('재해 확정 제출 입력', () => {
  it('새 제출은 배치·단가를 다시 보내지 않고 확정한 저장본만 참조한다', async () => {
    const design = { revision: 7, snapshotSha256: 'a'.repeat(64) };
    await submitSavedHistorical('seoul-20220808', 'saved-retry-key', design);
    expect(api).toHaveBeenLastCalledWith('/historical/designs/seoul-20220808/submissions', 'POST', {
      requestKey: 'saved-retry-key',
      ...design,
    });
  });
  it('다른 구의 배치도 전부 보내고 원 설치 시각과 실행 계보를 보존한다', async () => {
    const drafts = [
      {
        site: { districtId: '2419953', cellId: 'RW2' },
        facilityType: 'GREEN_ROOF',
        areaM2: 20,
        marker: { installedAt: '2022-08-08T09:02:17Z' },
      },
      {
        site: { districtId: '2410520', cellId: 'RW1' },
        facilityType: 'GREEN_ROOF',
        areaM2: 40,
        marker: { installedAt: '2022-08-08T10:01:57Z' },
      },
    ] as HistoricalDraft[];
    const placements = submissionPlacements(drafts, {
      hash: { id: 'previous', districtId: '2419953' } as HistoricalJob,
    });
    expect(placements.map((p) => p.districtId)).toEqual(['2410520', '2419953']);
    expect(placements[1].experimentId).toBe('previous');
    expect(placements[0].experimentId).toBeNull();
    expect(placements[0].installedAt).toBe('2022-08-08T10:01:57Z');
    await submitHistorical('seoul-20220808', 'same-retry-key', placements);
    expect(api).toHaveBeenCalledWith('/historical/submissions', 'POST', {
      eventId: 'seoul-20220808',
      requestKey: 'same-retry-key',
      placements,
    });
    expect(drafts[0].site.districtId).toBe('2419953');
  });
});
