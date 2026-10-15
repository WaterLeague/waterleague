import { api } from '../../../shared/repository/apiClient';
import {
  mapRequest,
  mapRequestDetail,
  mapRequestPage,
  mapReview,
  mapReviewPage,
} from '../mapper/utilizationMapper';
import type { Decision, ReviewState, UtilizationRequest } from '../entity/utilization';
const page = (after?: string | null) => (after ? '?after=' + encodeURIComponent(after) : '');
export const loadRequests = async (institution: boolean, after?: string | null) =>
  mapRequestPage(
    await api((institution ? '/institution' : '') + '/utilization/requests' + page(after))
  );
export const loadRequest = async (id: string) =>
  mapRequestDetail(await api('/utilization/requests/' + id));
export const decideRequest = async (r: UtilizationRequest, decision: Decision) =>
  mapRequest(
    await api('/utilization/requests/' + r.id + '/decisions', 'POST', {
      expectedRevision: r.revision,
      termsHash: r.termsHash,
      decision,
    })
  );
export const createRequest = async (
  jobId: string,
  title: string,
  purpose: string,
  requestKey: string
) =>
  mapRequest(
    await api('/institution/utilization/requests', 'POST', { jobId, title, purpose, requestKey })
  );
export const loadReviews = async (jobId?: string, after?: string | null) =>
  mapReviewPage(
    await api(
      (jobId ? '/research/strategies/' + jobId + '/reviews' : '/utilization/reviews') + page(after)
    )
  );
export const createReview = async (
  jobId: string,
  state: ReviewState,
  reason: string,
  limitations: string
) =>
  mapReview(
    await api('/research/strategies/' + jobId + '/reviews', 'POST', { state, reason, limitations })
  );
