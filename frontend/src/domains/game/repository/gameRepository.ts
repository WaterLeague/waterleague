import { api } from '../../../shared/repository/apiClient';
import { mapLab, mapRainfallCatalog } from '../mapper/labMapper';
import type {
  Placement,
  Version,
  StrategySummary,
  StrategyDetail,
  Job,
  Board,
} from '../entity/game';
export const loadLab = async (hash?: string) =>
  mapLab(await api<unknown>('/lab' + (hash ? '?modelHash=' + encodeURIComponent(hash) : '')));
export const loadRainfallCatalog = async () =>
  mapRainfallCatalog(await api<unknown>('/lab/catalog'));
export const loadStrategies = () => api<StrategySummary[]>('/strategies');
export const loadStrategy = (id: string) => api<StrategyDetail>('/strategies/' + id);
export const saveStrategy = (
  id: string | null,
  title: string,
  modelHash: string,
  placements: Placement[],
  designNote: string,
  baseRevision: number
) =>
  api<Version>(id ? '/strategies/' + id + '/versions' : '/strategies', 'POST', {
    title,
    modelHash,
    placements,
    designNote,
    baseRevision,
  });
export const enqueue = (versionId: string, requestKey: string) =>
  api<Job>('/simulations', 'POST', { versionId, requestKey });
export const loadJob = (id: string) => api<Job>('/simulations/' + id);
export const loadJobs = () => api<Job[]>('/simulations');
export const submit = (jobId: string) => api<{ score: number }>('/submissions', 'POST', { jobId });
export const loadBoard = (hash: string) =>
  api<Board>('/leaderboard?modelHash=' + encodeURIComponent(hash));
