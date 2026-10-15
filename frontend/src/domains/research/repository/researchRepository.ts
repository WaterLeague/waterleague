import { api } from '../../../shared/repository/apiClient';
import { mapLab } from '../../game/mapper/labMapper';
import type { Consent, ResearchEntry, ResearchDetail } from '../entity/research';
export const loadConsents = () => api<Consent[]>('/consents');
export const setConsent = (id: string, granted: boolean) =>
  api('/consents/' + id, 'PUT', { granted });
export const loadResearch = () => api<ResearchEntry[]>('/research/strategies');
export async function loadResearchDetail(id: string) {
  const detail = await api<ResearchDetail>('/research/strategies/' + id);
  return { ...detail, lab: mapLab(detail.lab) };
}
