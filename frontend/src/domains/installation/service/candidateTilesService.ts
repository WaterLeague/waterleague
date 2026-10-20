import type { FacilityType } from '../../game/entity/game';
export const candidateTypes = [
  'RAIN_GARDEN',
  'PERMEABLE_PAVEMENT',
  'GREEN_ROOF',
  'BIORETENTION',
  'VEGETATIVE_SWALE',
  'INFILTRATION_TRENCH',
] as const;
export type GroundCandidate = [
  cellId: string,
  districtId: string,
  mask: number,
  polygons: [number, number][][][],
];
export const candidateKey = (row: GroundCandidate) => row[1] + ':' + row[0];
export const candidateMask = (type: FacilityType | '') =>
  type ? 1 << candidateTypes.indexOf(type) : 0;
export function candidateMatches(row: GroundCandidate, type: FacilityType | '') {
  return !type || !!(row[2] & candidateMask(type));
}
export function candidateBounds(center: [number, number], distance: number) {
  const radius = Math.max(300, distance * 1.1);
  return [center[0] - radius, center[1] - radius, center[0] + radius, center[1] + radius];
}
