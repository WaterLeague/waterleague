import type { MapPolygons } from '../../catalog/service/mapGeometryService';
export type ParkingSlot = {
  center: [number, number];
  angle: number;
  corners: [number, number][];
  seed: number;
};
export type ParkingLot = {
  id: string;
  polygons: MapPolygons;
  surfacePolygons: MapPolygons;
  supports: { center: [number, number]; angle: number; width: number }[];
  bounds: [number, number, number, number];
  slots: ParkingSlot[];
};
export type ParkingData = {
  lots: ParkingLot[];
  displayRoadWidths: { id: string; lanes: number; widthM: number }[];
  routes: { id: string; reason: string; parts: [number, number][][] }[];
};
