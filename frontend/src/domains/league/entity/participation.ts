export type ParticipantState = 'PENDING' | 'APPROVED' | 'REJECTED' | 'WITHDRAWN';
export interface Participant {
  leagueId: string;
  ownerId: string;
  displayName: string;
  state: ParticipantState;
  revision: number;
  reviewRequired: boolean;
  rulesHash: string;
  createdAt: string;
  updatedAt: string;
}
export interface ParticipantEvent {
  revision: number;
  state: ParticipantState;
  reason: string;
  createdAt: string;
}
export interface LeagueTeam {
  id: string;
  name: string;
  captain: boolean;
  frozenAt: string | null;
  members: { displayName: string; captain: boolean; self: boolean; eligible: boolean }[];
  submissionCount: number;
  eligible: boolean;
  invitationActive: boolean;
}
export interface Participation {
  participant: Participant | null;
  events: ParticipantEvent[];
  team: LeagueTeam | null;
  submissionCount: number;
}
export interface ParticipationSummary {
  leagueId: string;
  title: string;
  organizationName: string;
  access: 'PUBLIC' | 'INVITE';
  state: ParticipantState;
  updatedAt: string;
}
export interface ParticipantPage {
  items: Participant[];
  nextCursor: string | null;
}
export interface TeamPreview {
  id: string;
  name: string;
  memberCount: number;
  teamSizeLimit: number;
  rulesHash: string;
}
