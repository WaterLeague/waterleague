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
// 도로·보도 표면 위에 후보를 표시하되 상부 건물·교량의 깊이 검사는 유지한다.
export const candidateSurfaceLift = 0.18;
export const candidateMask = (type: FacilityType | '') =>
  type ? 1 << candidateTypes.indexOf(type) : 0;
export function candidateMatches(row: GroundCandidate, type: FacilityType | '') {
  return !type || !!(row[2] & candidateMask(type));
}
export function candidateBounds(center: [number, number], distance: number) {
  const radius = Math.max(300, distance * 1.1);
  return [center[0] - radius, center[1] - radius, center[0] + radius, center[1] + radius];
}
export function nearbyCandidateTiles<T extends { id: string; bounds: readonly number[] }>(
  tiles: T[],
  center: [number, number],
  distance: number
) {
  if (!Number.isFinite(distance) || distance > 6500 || !center.every(Number.isFinite)) return [];
  const radius = Math.max(500, Math.min(2500, distance * 0.72));
  return tiles
    .filter(
      (t) =>
        t.bounds[0] <= center[0] + radius &&
        t.bounds[2] >= center[0] - radius &&
        t.bounds[1] <= center[1] + radius &&
        t.bounds[3] >= center[1] - radius
    )
    .sort((a, b) => {
      const d = (t: T) =>
        Math.hypot(
          (t.bounds[0] + t.bounds[2]) / 2 - center[0],
          (t.bounds[1] + t.bounds[3]) / 2 - center[1]
        );
      return d(a) - d(b) || a.id.localeCompare(b.id);
    });
}
export function mergeCandidateParts(tiles: GroundCandidate[][]): GroundCandidate[] {
  const grouped = new Map<string, GroundCandidate>();
  for (const rows of tiles)
    for (const row of rows) {
      const key = candidateKey(row),
        saved = grouped.get(key);
      if (saved) saved[3].push(...row[3]);
      else grouped.set(key, [row[0], row[1], row[2], [...row[3]]]);
    }
  return [...grouped.values()];
}
