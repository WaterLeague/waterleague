export interface District {
  id: string;
  name: string;
  mapId: string;
  modelHash: string;
  center: [number, number];
  stationId: string;
  stationName: string;
}
export type AffiliationType = 'RESIDENT' | 'AFFILIATED';
