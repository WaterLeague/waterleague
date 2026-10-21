import { api } from '../../../shared/repository/apiClient';
import {
  catalogDto,
  competitionDto,
  resultDto,
  candidatesDto,
  listDto,
  type CompetitionCreate,
} from '../dto/competitionDto';
const base = '/competitions';
export const loadCompetitionCatalog = async (signal?: AbortSignal) =>
  catalogDto.parse(await api(base + '/catalog', 'GET', undefined, signal));
export const loadCompetitions = async (page = 0, signal?: AbortSignal) =>
  listDto.parse(await api(`${base}?page=${page}`, 'GET', undefined, signal));
export const loadCompetition = async (id: string, signal?: AbortSignal) =>
  competitionDto.parse(await api(`${base}/${encodeURIComponent(id)}`, 'GET', undefined, signal));
export const createCompetition = async (body: CompetitionCreate) =>
  competitionDto.parse(await api(base, 'POST', body));
export const joinCompetition = async (id: string, rulesHash: string) =>
  competitionDto.parse(await api(`${base}/${id}/join`, 'POST', { rulesHash }));
export const cancelCompetition = async (id: string) =>
  competitionDto.parse(await api(`${base}/${id}/cancel`, 'POST'));
export const loadCompetitionResults = async (id: string, page = 0, signal?: AbortSignal) =>
  resultDto.parse(await api(`${base}/${id}/results?page=${page}`, 'GET', undefined, signal));
export const loadCompetitionCandidates = async (id: string, signal?: AbortSignal) =>
  candidatesDto.parse(await api(`${base}/${id}/candidates`, 'GET', undefined, signal));
export const submitCompetition = (id: string, jobId: string, rulesHash: string) =>
  api(`${base}/${id}/submissions`, 'POST', { jobId, rulesHash });
