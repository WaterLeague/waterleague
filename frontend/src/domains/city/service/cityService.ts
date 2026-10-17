import type { City } from '../entity/city';
export function nearbyTiles(city: City, center: [number, number], distance: number) {
  if (!Number.isFinite(distance) || distance > 6500 || !center.every(Number.isFinite)) return [];
  const radius = Math.max(900, distance * 0.75);
  return city.tiles
    .filter(
      (t) =>
        t.bounds[0] <= center[0] + radius &&
        t.bounds[2] >= center[0] - radius &&
        t.bounds[1] <= center[1] + radius &&
        t.bounds[3] >= center[1] - radius
    )
    .sort((a, b) => {
      const d = (t: typeof a) =>
        Math.hypot(
          (t.bounds[0] + t.bounds[2]) / 2 - center[0],
          (t.bounds[1] + t.bounds[3]) / 2 - center[1]
        );
      return d(a) - d(b) || a.id.localeCompare(b.id);
    })
    .slice(0, 16);
}
