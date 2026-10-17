import type { Placement } from '../../game/entity/game';

export interface ReferenceMetrics {
  accountedDischargeM3: number;
  runoffM3: number;
  finalStorageM3: number;
  runoffContinuityPercent: number;
}
export interface ReferenceEvaluation {
  modelHash: string;
  modelTitle: string;
  role: 'SEARCH_INPUT' | 'POST_SELECTION_COMPARISON';
  rainfall: {
    stationId: string;
    stationName: string;
    start: string;
    end: string;
    totalDepthMm: number;
  };
  score: number;
  baseline: ReferenceMetrics;
  strategy: ReferenceMetrics;
}
export interface ReferencePlan {
  id: string;
  title: string;
  budget: number;
  cost: number;
  placements: Placement[];
  candidateEvaluations: number;
  stages: {
    placements: Placement[];
    cost: number;
    accountedDischargeM3: number;
    incrementReductionM3: number;
  }[];
  stopReason: 'EVALUATION_LIMIT' | 'NO_POSITIVE_FEASIBLE_INCREMENT';
  sampleScoreRange: { min: number; max: number };
  evaluations: ReferenceEvaluation[];
}
export interface CpuReference {
  reportHash: string;
  report: {
    id: string;
    trainingModelHash: string;
    mapId?: string;
    mapTitle?: string;
    modelHashes: string[];
    uniqueCandidateEvaluations: number;
    totalCandidateRequests: number;
    createdAt: string;
    plans: ReferencePlan[];
    limitations: string[];
  };
}
