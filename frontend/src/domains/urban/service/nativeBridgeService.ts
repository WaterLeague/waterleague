import type { Terrain } from '../../terrain/entity/terrain';
import { terrainMeshHeight } from '../../terrain/service/terrainDrapeService';
type Polygons = [number, number][][][];
const flat = {};
const cache = new WeakMap<object, WeakMap<object, number>>();
const groupCache = new WeakMap<object, WeakMap<object, number>>();
export const nativeBridgeLiftM = 6.5;
export function withinBridge(point: readonly [number, number], polygons: Polygons) {
  const inside = (ring: [number, number][]) => {
    let value = false;
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      const a = ring[i],
        b = ring[j];
      if (
        a[1] > point[1] !== b[1] > point[1] &&
        point[0] < ((b[0] - a[0]) * (point[1] - a[1])) / (b[1] - a[1]) + a[0]
      )
        value = !value;
    }
    return value;
  };
  return polygons.some((p) => inside(p[0]) && !p.slice(1).some(inside));
}
export function nativeBridgeHeight(
  terrain: Terrain | null,
  polygons: Polygons,
  lift = nativeBridgeLiftM
) {
  const key = terrain ?? flat;
  let groups = groupCache.get(key);
  if (!groups) {
    groups = new WeakMap();
    groupCache.set(key, groups);
  }
  const known = groups.get(polygons);
  if (known !== undefined) return known + lift - nativeBridgeLiftM;
  let heights = cache.get(key);
  if (!heights) {
    heights = new WeakMap();
    cache.set(key, heights);
  }
  let result = -Infinity;
  for (const polygon of polygons) {
    let height = heights.get(polygon);
    if (height === undefined) {
      height = -Infinity;
      for (let i = 1; i < polygon[0].length; i++) {
        const a = polygon[0][i - 1],
          b = polygon[0][i];
        const steps = Math.max(1, Math.ceil(Math.hypot(b[0] - a[0], b[1] - a[1]) / 30));
        for (let j = 0; j <= steps; j++)
          height = Math.max(
            height,
            terrainMeshHeight(terrain, [
              a[0] + ((b[0] - a[0]) * j) / steps,
              a[1] + ((b[1] - a[1]) * j) / steps,
            ])
          );
      }
      height += nativeBridgeLiftM;
      heights.set(polygon, height);
    }
    result = Math.max(result, height);
  }
  groups.set(polygons, result);
  return result + lift - nativeBridgeLiftM;
}
export function nativeBridgeProfileHeight(
  terrain: Terrain | null,
  point: readonly [number, number],
  profile: import('../dto/nativeBridgeDto').NativeBridgeProfile
) {
  const ground = terrainMeshHeight(terrain, point),
    deck = nativeBridgeHeight(terrain, profile.deckPolygons, profile.deckLiftM);
  let nearest = Infinity,
    along = 0,
    walked = 0;
  for (let i = 1; i < profile.coordinates.length; i++) {
    const a = profile.coordinates[i - 1],
      b = profile.coordinates[i],
      dx = b[0] - a[0],
      dy = b[1] - a[1],
      length = Math.hypot(dx, dy),
      t = Math.max(
        0,
        Math.min(1, ((point[0] - a[0]) * dx + (point[1] - a[1]) * dy) / (length * length || 1))
      ),
      distance = (point[0] - a[0] - dx * t) ** 2 + (point[1] - a[1] - dy * t) ** 2;
    if (distance < nearest) {
      nearest = distance;
      along = walked + t * length;
    }
    walked += length;
  }
  const [start, end] = profile.span;
  let mix =
    along < start
      ? start
        ? along / start
        : 1
      : along > end
        ? walked > end
          ? (walked - along) / (walked - end)
          : 1
        : 1;
  mix = Math.max(0, Math.min(1, mix));
  mix = mix * mix * (3 - 2 * mix);
  if (profile.steps) {
    const steps = Math.max(1, Math.ceil(walked / 0.32));
    mix = Math.min(1, Math.ceil(mix * steps) / steps);
  }
  return Math.max(ground, ground + (deck - ground) * mix);
}
