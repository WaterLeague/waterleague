import type { TopographyIndex } from '../dto/topographyDto';
export function nearbyTopographyTiles(
  index: TopographyIndex,
  center: [number, number],
  distance: number
) {
  if (!Number.isFinite(distance) || distance > 6500 || !center.every(Number.isFinite)) return [];
  const radius = Math.max(500, Math.min(2500, distance * 0.72));
  return index.tiles
    .filter(
      (tile) =>
        tile.bounds[0] <= center[0] + radius &&
        tile.bounds[2] >= center[0] - radius &&
        tile.bounds[1] <= center[1] + radius &&
        tile.bounds[3] >= center[1] - radius
    )
    .sort((a, b) => {
      const d = (tile: typeof a) =>
        Math.hypot(
          (tile.bounds[0] + tile.bounds[2]) / 2 - center[0],
          (tile.bounds[1] + tile.bounds[3]) / 2 - center[1]
        );
      return d(a) - d(b) || a.id.localeCompare(b.id);
    });
}
