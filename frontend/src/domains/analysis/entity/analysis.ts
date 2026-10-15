import type { Job, FacilityType } from '../../game/entity/game';
import type { RainfallComparison } from '../../comparison/entity/comparison';
export interface ResearchComparisonSummary {
  id: string;
  sourceJobId: string;
  title: string;
  createdAt: string;
}
export interface ResearchComparison {
  id: string;
  organizationId: string;
  sourceJobId: string;
  requestHash: string;
  createdAt: string;
  sourceSimulation: Job;
  comparison: RainfallComparison;
}
export interface PatternAnalysis {
  modelHash: string;
  method: 'SELECTED_UNIQUE_INPUT_TOP_K_WITH_TIES_V1';
  requestedCount: number;
  uniqueInputCount: number;
  duplicateInputCount: number;
  topK: number;
  includedCount: number;
  cutoffScore: number;
  designs: { jobId: string; inputHash: string; score: number; costKrw: number }[];
  placements: {
    cellId: string;
    facilityType: FacilityType;
    designCount: number;
    frequencyPercent: number;
    minimumAreaM2: number;
    maximumAreaM2: number;
    meanInstalledAreaM2: number;
    meanAllDesignAreaM2: number;
  }[];
  facilityPairs: {
    first: FacilityType;
    second: FacilityType;
    designCount: number;
    frequencyPercent: number;
  }[];
  minimumCostKrw: number;
  maximumCostKrw: number;
  minimumScore: number;
  maximumScore: number;
  limitations: string[];
}
