import type { InitializationEvidenceData } from '../../physics/entity/initialization';
import type { InitializationSensitivityData } from '../../physics/dto/initializationSensitivityDto';
import type { FacilityEvidence } from '../../facility/dto/facilityDto';
import type { SharedSite, SharedInstallation } from '../../installation/entity/installation';
import type { FacilityType } from '../../game/entity/game';
import type { CostRecord } from '../../cost/dto/costDto';
import type { RunoffComparisonData } from '../../physics/dto/runoffComparisonDto';
export interface HistoricalDraft {
  site: SharedSite;
  facilityType: FacilityType;
  areaM2: number;
  marker: SharedInstallation;
}
export interface HistoricalScoreFrame {
  at: string;
  differenceM3: number;
  baselineAccountedM3: number;
  designAccountedM3: number;
}
export interface HistoricalJob {
  id: string;
  districtId: string;
  modelHash: string;
  state: 'QUEUED' | 'RUNNING' | 'SUCCEEDED' | 'FAILED' | 'REJECTED';
  createdAt: string;
  placements: {
    districtId: string;
    cellId: string;
    facilityType: FacilityType;
    areaM2: number;
    siteModelHash: string;
    installedAt?: string;
    temporalPolicy?: 'INSTALLATION_TIME_EXPERIMENT_V1';
    parentExperimentId?: string;
  }[];
  message: string;
  result: null | {
    engineVersion: string;
    validationLevel: 'EXPLORATORY';
    differenceM3: number;
    baselineAccountedM3: number;
    designAccountedM3: number;
    stationName: string;
    start: string;
    end: string;
    assumptions: string[];
    temporalPolicy?: 'INSTALLATION_TIME_EXPERIMENT_V1';
    initializationSensitivity?: InitializationSensitivityData;
    facilities?: {
      cellId: string;
      installedAt?: string;
      frames?: HistoricalScoreFrame[];
      initialization?: InitializationEvidenceData | null;
      facilityDesign?: FacilityEvidence | null;
      costRecord?: CostRecord;
      runoffComparison?: RunoffComparisonData;
    }[];
    frames: {
      at: string;
      rainMm: number;
      baselineM3s: number;
      designM3s: number;
      differenceM3: number;
      baselineAccountedM3?: number;
      designAccountedM3?: number;
    }[];
  };
}
