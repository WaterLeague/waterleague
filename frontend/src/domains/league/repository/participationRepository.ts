import { z } from 'zod';
import { api } from '../../../shared/repository/apiClient';
import { mapLeague } from '../mapper/leagueMapper';
import {
  mapParticipation,
  mapParticipantPage,
  parseParticipationData as parse,
} from '../mapper/participationMapper';
import {
  eventDto,
  summaryDto,
  participantDto,
  teamPreviewDto,
  invitationDto,
  invitationStatusDto,
  teamCreatedDto,
} from '../dto/participationDto';
const path = (id: string) => '/leagues/' + id;
const managed = (id: string) => '/institution' + path(id);
export const loadApplications = async () =>
  parse(z.array(summaryDto).max(100), await api('/leagues/participations'));
export const loadParticipation = async (id: string, owner: string) =>
  mapParticipation(await api(path(id) + '/participation'), id, owner);
export const previewInvitation = async (code: string) =>
  mapLeague(await api('/leagues/invitations/preview', 'POST', { code }));
export const join = async (id: string, rulesHash: string, code?: string) =>
  api(path(id) + '/participation', 'POST', { rulesHash, ...(code ? { code } : {}) });
export const withdraw = (id: string, revision: number) =>
  api(path(id) + '/participation/withdraw', 'POST', { revision });
export const participants = async (id: string, after?: string) =>
  mapParticipantPage(
    await api(managed(id) + '/participants' + (after ? '?after=' + encodeURIComponent(after) : '')),
    id
  );
export const events = async (id: string, owner: string) =>
  parse(z.array(eventDto).max(100), await api(managed(id) + '/participants/' + owner + '/events'));
export const decide = async (
  id: string,
  owner: string,
  revision: number,
  state: 'APPROVED' | 'REJECTED',
  reason: string
) =>
  parse(
    participantDto,
    await api(managed(id) + '/participants/' + owner + '/decisions', 'POST', {
      revision,
      state,
      reason,
    })
  );
export const invitationStatus = async (id: string) =>
  parse(invitationStatusDto, await api(managed(id) + '/invitation'));
export const issueInvitation = async (id: string) =>
  parse(invitationDto, await api(managed(id) + '/invitation', 'POST'));
export const revokeInvitation = (id: string) => api(managed(id) + '/invitation', 'DELETE');
export const createTeam = async (id: string, name: string) =>
  parse(teamCreatedDto, await api(path(id) + '/teams', 'POST', { name }));
export const previewTeam = async (id: string, code: string) =>
  parse(teamPreviewDto, await api(path(id) + '/teams/preview', 'POST', { code }));
export const joinTeam = (id: string, code: string, teamId: string, rulesHash: string) =>
  api(path(id) + '/teams/join', 'POST', { code, teamId, rulesHash });
export const leaveTeam = (id: string) => api(path(id) + '/teams/leave', 'POST');
export const issueTeamInvitation = async (id: string) =>
  parse(invitationDto, await api(path(id) + '/teams/invitation', 'POST'));
export const revokeTeamInvitation = (id: string) => api(path(id) + '/teams/invitation', 'DELETE');
