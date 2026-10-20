import type { Terrain } from '../../terrain/entity/terrain';
import { terrainMeshHeight } from '../../terrain/service/terrainDrapeService';
type Polygons = [number, number][][][];
const cache = new WeakMap<Terrain, WeakMap<Polygons, number>>();
export function buildingBaseElevation(terrain: Terrain | null, polygons: Polygons) {
  if (!terrain) return 0;
  let heights = cache.get(terrain);
  if (!heights) {
    heights = new WeakMap();
    cache.set(terrain, heights);
  }
  const known = heights.get(polygons);
  if (known !== undefined) return known;
  let elevation = -Infinity;
  for (const polygon of polygons)
    for (const ring of polygon)
      for (let i = 1; i < ring.length; i++) {
        const a = ring[i - 1],
          b = ring[i];
        const steps = Math.max(1, Math.ceil(Math.hypot(b[0] - a[0], b[1] - a[1]) / 30));
        for (let s = 0; s <= steps; s++)
          elevation = Math.max(
            elevation,
            terrainMeshHeight(terrain, [
              a[0] + ((b[0] - a[0]) * s) / steps,
              a[1] + ((b[1] - a[1]) * s) / steps,
            ])
          );
      }
  const value = Number.isFinite(elevation) ? elevation + 0.03 : 0;
  heights.set(polygons, value);
  return value;
}
