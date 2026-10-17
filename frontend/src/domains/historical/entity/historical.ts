import type { InitializationEvidenceData } from '../../physics/entity/initialization';
import type { FacilityEvidence } from '../../facility/dto/facilityDto';
import type { SharedSite, SharedInstallation } from '../../installation/entity/installation';
import type { FacilityType } from '../../game/entity/game';
export interface HistoricalDraft {
  site: SharedSite;
  facilityType: FacilityType;
  areaM2: number;
  marker: SharedInstallation;
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
    facilities?: {
      cellId: string;
      initialization?: InitializationEvidenceData | null;
      facilityDesign?: FacilityEvidence | null;
    }[];
    frames: {
      at: string;
      rainMm: number;
      baselineM3s: number;
      designM3s: number;
      differenceM3: number;
    }[];
  };
}
