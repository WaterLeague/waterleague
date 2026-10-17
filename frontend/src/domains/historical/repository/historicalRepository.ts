import { api } from '../../../shared/repository/apiClient';
import type { HistoricalJob, HistoricalDraft } from '../entity/historical';
export const listHistorical = () => api<HistoricalJob[]>('/historical');
export const loadHistorical = (id: string) => api<HistoricalJob>('/historical/' + id);
export const runHistorical = (
  districtId: string,
  modelHash: string,
  drafts: HistoricalDraft[],
  requestKey: string
) =>
  api<HistoricalJob>('/historical', 'POST', {
    requestKey,
    districtId,
    modelHash,
    placements: drafts.map((d) => ({
      cellId: d.site.cellId,
      facilityType: d.facilityType,
      areaM2: d.areaM2,
    })),
  });
