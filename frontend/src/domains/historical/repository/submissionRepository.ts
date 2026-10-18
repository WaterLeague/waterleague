import { api } from '../../../shared/repository/apiClient';
import type { HistoricalDraft, HistoricalJob } from '../entity/historical';
import type { HistoricalSubmission, HistoricalBoard } from '../entity/historicalSubmission';

export const loadSubmission = (id: string) =>
  api<HistoricalSubmission>('/historical/submissions/' + id);
export const listSubmissions = (eventId: string) =>
  api<HistoricalSubmission[]>('/historical/submissions?eventId=' + encodeURIComponent(eventId));
export const loadHistoricalBoard = (eventId: string) =>
  api<HistoricalBoard>('/historical/leaderboard/' + encodeURIComponent(eventId));
export function submissionPlacements(
  drafts: HistoricalDraft[],
  jobs: Record<string, HistoricalJob>
) {
  return drafts
    .map((d) => ({
      districtId: d.site.districtId,
      cellId: d.site.cellId,
      facilityType: d.facilityType,
      areaM2: d.areaM2,
      installedAt: d.marker.installedAt,
      experimentId: Object.values(jobs).find((j) => j.districtId === d.site.districtId)?.id ?? null,
    }))
    .sort((a, b) => a.districtId.localeCompare(b.districtId) || a.cellId.localeCompare(b.cellId));
}
export const submitHistorical = (
  eventId: string,
  requestKey: string,
  placements: ReturnType<typeof submissionPlacements>
) =>
  api<HistoricalSubmission>('/historical/submissions', 'POST', { eventId, requestKey, placements });
