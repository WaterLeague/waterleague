import { api } from '../../../shared/repository/apiClient';
import { sharedConsentsDto, sharedRecordsDto, sharedDetailDto } from '../dto/sharedResearchDto';
export const recordsPath = (institution: boolean) =>
  institution ? '/research/installations' : '/installations/records';
export const loadConsents = async () => sharedConsentsDto.parse(await api('/consents/shared'));
export const setConsent = (id: string, granted: boolean) =>
  api('/consents/shared/' + id, 'PUT', { granted });
export const loadRecords = async (institution: boolean, week: string) =>
  sharedRecordsDto.parse(
    await api(recordsPath(institution) + '?weekStart=' + encodeURIComponent(week))
  );
export const loadDetail = async (institution: boolean, id: string) =>
  sharedDetailDto.parse(await api(recordsPath(institution) + '/' + id));
