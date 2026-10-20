import { api } from '../../../shared/repository/apiClient';
import type { HistoricalDraft, HistoricalJob } from '../entity/historical';
import { historicalSubmissionDto, historicalBoardDto } from '../dto/submissionDto';

export const loadSubmission = (id: string) =>
  api('/historical/submissions/' + id).then((v) => historicalSubmissionDto.parse(v));
export const listSubmissions = (eventId: string) =>
  api('/historical/submissions?eventId=' + encodeURIComponent(eventId)).then((v) =>
    historicalSubmissionDto.array().parse(v)
  );
export const loadHistoricalBoard = (eventId: string) =>
  api('/historical/leaderboard/' + encodeURIComponent(eventId)).then((v) =>
    historicalBoardDto.parse(v)
  );
export type SubmissionDesign = { revision: number; snapshotSha256: string };
export const submitSavedHistorical = (
  eventId: string,
  requestKey: string,
  design: SubmissionDesign
) =>
  api('/historical/designs/' + encodeURIComponent(eventId) + '/submissions', 'POST', {
    requestKey,
    ...design,
  }).then((v) => historicalSubmissionDto.parse(v));
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
  api('/historical/submissions', 'POST', { eventId, requestKey, placements }).then((v) =>
    historicalSubmissionDto.parse(v)
  );
