import type { FacilityType, Lab, Board } from '../../game/entity/game';
export interface LeagueRules {
  schemaVersion: 1 | 2 | 3;
  modelHash: string;
  engineRevision: string;
  generatorSha256: string;
  scoreRule: 'ACCOUNTED_DISCHARGE_REDUCTION_V1';
  currency: 'KRW';
  budget: number;
  allowedTypes: FacilityType[];
  submissionLimit: number;
  opensAt: string;
  closesAt: string;
  validationLevel: 'EXPLORATORY';
  official: false;
  placementLimit?: number | null;
  areaLimitM2?: number | null;
  award?: LeagueAward | null;
  participation?: LeagueParticipationRules | null;
}
export interface LeagueParticipationRules {
  access: 'PUBLIC' | 'INVITE';
  admission: 'OPEN' | 'APPROVAL';
  entryMode: 'INDIVIDUAL' | 'TEAM';
  teamSizeLimit: number | null;
}
export interface LeagueAward {
  prizeKrw: number;
  winnerCount: number;
  notice: string;
}
export interface League {
  id: string;
  organizationId: string;
  organizationName: string;
  revision: number;
  state: 'DRAFT' | 'PUBLISHED' | 'CANCELLED';
  phase: 'DRAFT' | 'SCHEDULED' | 'OPEN' | 'CLOSED' | 'CANCELLED';
  title: string;
  question: string;
  rules: LeagueRules;
  rulesHash: string;
  executionHash: string | null;
  publishedAt: string | null;
  cancellationReason: string | null;
  playable: boolean;
}
export interface LeagueDetail {
  league: League;
  lab: Lab;
  entries: Board['entries'];
  boardVisible?: boolean;
}
export interface LeagueDraft {
  modelHash: string;
  baseRevision: number;
  title: string;
  question: string;
  opensAt: string;
  closesAt: string;
  budget: number;
  allowedTypes: FacilityType[];
  submissionLimit: number;
  placementLimit: number;
  areaLimitM2: number;
  award: LeagueAward;
}
export interface OwnSubmission {
  jobId: string;
  score: number;
  cost: number;
  submittedAt: string;
}
