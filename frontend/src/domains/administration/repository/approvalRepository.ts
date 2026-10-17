import { api } from '../../../shared/repository/apiClient';
import { mapApplications } from '../mapper/applicationMapper';
import type { Review } from '../entity/application';
export const loadApplications = async (status: string, after = '') =>
  mapApplications(
    await api(
      '/admin/members?status=' + encodeURIComponent(status) + '&after=' + encodeURIComponent(after)
    )
  );
export const loadReviews = (id: string) => api<Review[]>('/admin/members/' + id + '/reviews');
export const loadOrganizations = () => api<{ id: string; name: string }[]>('/organizations');
export const reviewApplication = (
  id: string,
  decision: string,
  expectedStatus: string,
  reason: string,
  organizationId: string
) =>
  api('/admin/members/' + id + '/reviews', 'POST', {
    decision,
    expectedStatus,
    reason,
    ...(organizationId ? { organizationId } : {}),
  });
