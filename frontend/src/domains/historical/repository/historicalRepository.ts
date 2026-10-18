import { api } from '../../../shared/repository/apiClient';
import type { HistoricalJob, HistoricalDraft } from '../entity/historical';
import { temporalPolicy } from '../service/temporalService';
export const listHistorical = () => api<HistoricalJob[]>('/historical');
export const loadHistorical = (id: string) => api<HistoricalJob>('/historical/' + id);
export const runHistorical = (
  districtId: string,
  modelHash: string,
  drafts: HistoricalDraft[],
  requestKey: string,
  sensitivityCellId?: string,
  parentExperimentId?: string
) =>
  api<HistoricalJob>('/historical', 'POST', {
    requestKey,
    districtId,
    modelHash,
    temporalPolicy,
    ...(parentExperimentId ? { parentExperimentId } : {}),
    ...(sensitivityCellId ? { sensitivityCellId } : {}),
    placements: drafts.map((d) => ({
      cellId: d.site.cellId,
      siteModelHash: d.site.modelHash,
      facilityType: d.facilityType,
      areaM2: d.areaM2,
      installedAt: d.marker.installedAt,
    })),
  });
