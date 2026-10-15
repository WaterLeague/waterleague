import type { Job, Version, Lab } from '../../game/entity/game';
export interface Consent {
  organizationId: string;
  name: string;
  granted: boolean;
}
export interface ResearchEntry {
  jobId: string;
  score: number;
  cost: number;
  designNote: string;
  revision: number;
  submittedAt: string;
}
export interface ResearchDetail {
  lab: Lab;
  simulation: Job;
  version: Version;
  history: Version[];
  leagueContexts?: {
    id: string;
    title: string;
    state: string;
    rulesHash: string;
    cancellationReason: string;
  }[];
}
