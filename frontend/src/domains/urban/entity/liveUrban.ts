export type UrbanArea = {
  id: string;
  name: string;
  areaKm2: number;
  bounds: [number, number, number, number];
  polygons: [number, number][][][];
};
type Provenance = { retrievedAt: string; validUntil: string; sourceSha256: string };
export type LivePopulation = Provenance & {
  minimum: number;
  maximum: number;
  sourceHourKst: number;
  congestion: string;
};
export type LiveTraffic = Provenance & { speedKmh: number; observedAt: string };
export type LivePlace = UrbanArea & {
  population: LivePopulation | null;
  traffic: LiveTraffic | null;
};
