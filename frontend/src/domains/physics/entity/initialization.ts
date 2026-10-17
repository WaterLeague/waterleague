export interface InitializationEvidenceData {
  method: string;
  warmupRainMm: number;
  warmupMinutes: number;
  initialSoilMoisture: number | null;
  initialStorageM3: number;
  aggregateDerivedMinutes?: number;
  limitations?: string[];
}
