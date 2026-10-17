export type MapPoint = [number, number];
export interface FacilityFootprint {
  polygons: MapPoint[][];
  boundary: [MapPoint, MapPoint][];
  area: number;
}
