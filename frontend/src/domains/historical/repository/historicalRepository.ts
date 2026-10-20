import { api } from '../../../shared/repository/apiClient';
import type { HistoricalJob, HistoricalDraft } from '../entity/historical';
import { temporalPolicy } from '../service/temporalService';
export const listHistorical = (guest = false) =>
  api<HistoricalJob[]>(guest ? '/guest-historical' : '/historical');
export const loadHistorical = (id: string, guest = false) =>
  api<HistoricalJob>((guest ? '/guest-historical/' : '/historical/') + id);
export const runHistorical = (
  districtId: string,
  modelHash: string,
  drafts: HistoricalDraft[],
  requestKey: string,
  sensitivityCellId?: string,
  parentExperimentId?: string,
  design?: { revision: number; eventId: string },
  pavementComparisonCellId?: string
) =>
  api<HistoricalJob>('/historical', 'POST', {
    requestKey,
    districtId,
    modelHash,
    temporalPolicy,
    ...(design ? { designRevision: design.revision, eventId: design.eventId } : {}),
    ...(parentExperimentId ? { parentExperimentId } : {}),
    ...(sensitivityCellId ? { sensitivityCellId } : {}),
    ...(pavementComparisonCellId ? { pavementComparisonCellId } : {}),
    placements: drafts.map((d) => ({
      cellId: d.site.cellId,
      siteModelHash: d.site.modelHash,
      facilityType: d.facilityType,
      areaM2: d.areaM2,
      installedAt: d.marker.installedAt,
    })),
  });

export const runGuestHistorical = (
  eventId: string,
  districtId: string,
  drafts: HistoricalDraft[],
  requestKey: string
) =>
  api<HistoricalJob>('/guest-historical', 'POST', {
    requestKey,
    eventId,
    districtId,
    placements: drafts.map((d) => ({
      districtId: d.site.districtId,
      placement: {
        cellId: d.site.cellId,
        siteModelHash: d.site.modelHash,
        facilityType: d.facilityType,
        areaM2: d.areaM2,
        installedAt: d.marker.installedAt,
      },
    })),
  });
