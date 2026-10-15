import { api } from '../../../shared/repository/apiClient';
import { mapLeague, mapLeagues } from '../mapper/leagueMapper';
import { mapLab } from '../../game/mapper/labMapper';
import { LeagueDataError } from '../exception/LeagueDataError';
import type { LeagueDetail, LeagueDraft, OwnSubmission } from '../entity/league';
export async function loadLeagues(managed = false) {
  return mapLeagues(await api(managed ? '/institution/leagues' : '/leagues'));
}
export async function loadLeague(id: string): Promise<LeagueDetail> {
  const d = await api<LeagueDetail>('/leagues/' + id);
  const league = mapLeague(d.league),
    lab = mapLab(d.lab);
  if (league.rules.modelHash !== lab.modelHash) throw new LeagueDataError();
  return { ...d, league, lab };
}
export const loadOwn = (id: string) => api<OwnSubmission[]>('/leagues/' + id + '/mine');
export const submit = (id: string, jobId: string, rulesHash: string) =>
  api('/leagues/' + id + '/submissions', 'POST', { jobId, rulesHash });
export async function saveDraft(id: string | null, draft: LeagueDraft) {
  return mapLeague(
    await api('/institution/leagues' + (id ? '/' + id : ''), id ? 'PUT' : 'POST', draft)
  );
}
export async function publish(id: string, revision: number, rulesHash: string) {
  return mapLeague(
    await api('/institution/leagues/' + id + '/publish', 'POST', { revision, rulesHash })
  );
}
export async function cancel(id: string, reason: string) {
  return mapLeague(await api('/institution/leagues/' + id + '/cancel', 'POST', { reason }));
}
