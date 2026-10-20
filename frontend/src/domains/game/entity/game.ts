export type RainfallUse =
  | 'COMMON_OBSERVED_REPLAY_NOT_LOCAL_OBSERVATION'
  | 'NEAREST_AWS_OBSERVED_REPLAY'
  | 'OBSERVED_REPLAY';
export type LegacyFacilityType = 'RAIN_GARDEN' | 'PERMEABLE_PAVEMENT' | 'GREEN_ROOF';
export type FacilityType =
  | LegacyFacilityType
  | 'BIORETENTION'
  | 'VEGETATIVE_SWALE'
  | 'INFILTRATION_TRENCH'
  | 'RAINWATER_CISTERN';
export type UnitCosts = Record<LegacyFacilityType, number> & {
  BIORETENTION?: number;
  VEGETATIVE_SWALE?: number;
  INFILTRATION_TRENCH?: number;
  RAINWATER_CISTERN?: number;
};
export interface Placement {
  cellId: string;
  facilityType: FacilityType;
  areaM2: number;
}
export interface Cell {
  id: string;
  name: string;
  buildingId?: string;
  kind: 'ROOF' | 'GROUND';
  coordinates: [number, number][];
  center: [number, number];
  heightM: number;
  areaM2: number;
  maxAreaM2: number;
  allowedTypes: FacilityType[];
  areaEvidence: string;
  eligibilityEvidence: string;
}
export interface Rainfall {
  start: string;
  end: string;
  intervalSeconds: number;
  depthsMm: number[];
  totalDepthMm: number;
  provider: string;
  stationName: string;
  stationId: string;
  quality: string;
  sourceHash: string;
  sourceUrl: string;
  checks: string[];
  limitations: string[];
  attribution: string;
  stationDistanceKm?: number;
  stationDistanceEvidence?: string;
  windowStatistics?: {
    peak15MinuteMm: number;
    peak60MinuteMm: number;
    observedDryLeadMinutes: number;
    observedDryTailMinutes: number;
  };
}
export interface Lab {
  modelHash: string;
  model: {
    id: string;
    title: string;
    mapId?: string;
    mapTitle?: string;
    regionalRainfallUse?: RainfallUse;
    validationLevel: 'EXPLORATORY';
    officialEvaluationAvailable: false;
    simulationAvailable: boolean;
    engine: string;
    currency: 'KRW';
    costModel: {
      currency: 'KRW';
      source?: { url: string } | null;
      evidence: string;
      note: string;
      exclusions: string[];
    };
    budget: number;
    maxPlacements: number;
    unitCosts: UnitCosts;
    cells: Cell[];
    rainfall: Rainfall;
    assumptions: string[];
    scoreRule: string;
  };
}
export interface Version {
  id: string;
  strategyId: string;
  revision: number;
  modelHash: string;
  inputHash: string;
  placements: Placement[];
  designNote: string;
  cost: number;
  currency: string;
  createdAt: string;
  events: { kind: string; before: Placement[]; after: Placement[] };
}
export interface StrategySummary {
  id: string;
  title: string;
  revision: number;
  updatedAt: string;
}
export interface StrategyDetail {
  id: string;
  title: string;
  versions: Version[];
}
export interface Metrics {
  runoffM3: number;
  surfaceRunoffM3: number;
  lidDrainageM3: number;
  finalStorageM3: number;
  initialStorageM3: number;
  accountedDischargeM3: number;
  infiltrationM3: number;
  evaporationM3: number;
  precipitationM3: number;
  runoffContinuityPercent: number;
  peakM3s: number;
  seriesM3s: number[];
}
export interface SimulationResult {
  execution?: {
    schema: 1;
    mode: 'COMPUTED' | 'REUSED';
    computationKey: string;
  };
  score: number;
  official: false;
  validationLevel: 'EXPLORATORY';
  baseline: Metrics;
  strategy: Metrics;
  assumptions: string[];
  sensitivity: { conductivityFactor: number; score: number; runoffM3: number }[];
  engine: { version: string; binarySha256: string; generatorSha256: string; platform: string };
}
export interface Job {
  id: string;
  versionId: string;
  state: 'QUEUED' | 'RUNNING' | 'SUCCEEDED' | 'FAILED' | 'REJECTED';
  result: SimulationResult | null;
  errorCode: string | null;
  createdAt: string;
  modelHash: string;
  inputHash: string;
}
export interface RainfallCatalog {
  defaultModelHash: string;
  models: {
    modelHash: string;
    title: string;
    mapId?: string;
    mapTitle?: string;
    budget: number;
    validationLevel: 'EXPLORATORY';
    official: false;
    regionalRainfallUse?: RainfallUse;
    rainfall: Omit<Rainfall, 'depthsMm'>;
  }[];
}
