import { streetLane, pathPosition } from './streetLifeService';
import type { SurfaceFrame } from '../../surface/entity/surface';
import type { TraceTile } from '../../floodtrace/entity/floodTrace';
import type { StreetPath } from './streetLifeService';
export type FloodContact = {
  kind: 'calculated' | 'record';
  depth: number | null;
  speed: number | null;
  hazard: number | null;
};
type Point = readonly [number, number];
type Triangle = { vertices: readonly [Point, Point, Point]; contact: FloodContact };
export type FloodBand = { from: number; to: number; contact: FloodContact };
export type FloodRoute = { length: number; bands: FloodBand[]; samples: FloodBand[] };
const BUCKET = 128;
const indexes = new WeakMap<object, ReturnType<typeof spatialIndex>>();
const identities = new WeakMap<object, number>();
let sequence = 0;
const fields = new Map<string, ReturnType<typeof field>>();
export function floodHazard(depth: number, speed: number) {
  const limits = [
    [0.3, 0.3, 2],
    [0.6, 0.5, 2],
    [0.6, 1.2, 2],
    [1, 2, 2],
    [4, 4, 4],
  ];
  const i = limits.findIndex(
    ([product, d, v]) => depth * speed <= product && depth <= d && speed <= v
  );
  return i < 0 ? 6 : i + 1;
}
export function stronger(a: FloodContact, b: FloodContact) {
  if (a.kind !== b.kind) return a.kind === 'calculated' ? a : b;
  return (a.hazard ?? 0) > (b.hazard ?? 0) ||
    ((a.hazard ?? 0) === (b.hazard ?? 0) && (a.depth ?? 0) >= (b.depth ?? 0))
    ? a
    : b;
}
function spatialIndex(triangles: Triangle[]) {
  const buckets = new Map<string, Triangle[]>(),
    broad: Triangle[] = [];
  const bounds = (points: readonly Point[]) => [
    Math.floor(Math.min(...points.map((p) => p[0])) / BUCKET),
    Math.floor(Math.min(...points.map((p) => p[1])) / BUCKET),
    Math.floor(Math.max(...points.map((p) => p[0])) / BUCKET),
    Math.floor(Math.max(...points.map((p) => p[1])) / BUCKET),
  ];
  for (const triangle of triangles) {
    const [x0, y0, x1, y1] = bounds(triangle.vertices);
    if ((x1 - x0 + 1) * (y1 - y0 + 1) > 256) {
      broad.push(triangle);
      continue;
    }
    for (let x = x0; x <= x1; x++)
      for (let y = y0; y <= y1; y++) {
        const key = x + ':' + y,
          values = buckets.get(key) ?? [];
        values.push(triangle);
        buckets.set(key, values);
      }
  }
  return (a: Point, b: Point) => {
    const [x0, y0, x1, y1] = bounds([a, b]);
    if ((x1 - x0 + 1) * (y1 - y0 + 1) > 1024) return triangles;
    const found = new Set(broad);
    for (let x = x0; x <= x1; x++)
      for (let y = y0; y <= y1; y++) for (const t of buckets.get(x + ':' + y) ?? []) found.add(t);
    return found;
  };
}
function sourceIndex(source: SurfaceFrame | TraceTile) {
  const previous = indexes.get(source);
  if (previous) return previous;
  const triangles: Triangle[] = [];
  if ('cells' in source)
    for (const cell of source.cells) {
      if (cell.depthM <= 1e-6) continue;
      triangles.push({
        vertices: cell.vertices,
        contact: {
          kind: 'calculated',
          depth: cell.depthM,
          speed: cell.speedMps,
          hazard: floodHazard(cell.depthM, cell.speedMps),
        },
      });
    }
  else
    for (let i = 0; i < source.triangleVertices.length; i += 6) {
      const v = source.triangleVertices;
      triangles.push({
        vertices: [
          [v[i], v[i + 1]],
          [v[i + 2], v[i + 3]],
          [v[i + 4], v[i + 5]],
        ],
        contact: { kind: 'record', depth: null, speed: null, hazard: null },
      });
    }
  const index = spatialIndex(triangles);
  indexes.set(source, index);
  return index;
}
// 선분을 삼각형의 세 반평면으로 자르므로 얇은 침수 구간도 배속과 무관하게 검출한다.
export function triangleIntersection(a: Point, b: Point, vertices: readonly [Point, Point, Point]) {
  const [p, q, r] = vertices,
    cross = (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0]);
  if (Math.abs(cross) < 1e-10) return null;
  const sign = Math.sign(cross);
  let low = 0,
    high = 1;
  for (let i = 0; i < 3; i++) {
    const u = vertices[i],
      v = vertices[(i + 1) % 3],
      ex = v[0] - u[0],
      ey = v[1] - u[1];
    const start = sign * (ex * (a[1] - u[1]) - ey * (a[0] - u[0]));
    const change = sign * (ex * (b[1] - a[1]) - ey * (b[0] - a[0]));
    if (Math.abs(change) < 1e-12) {
      if (start < -1e-8) return null;
    } else if (change > 0) low = Math.max(low, -start / change);
    else high = Math.min(high, -start / change);
    if (low > high + 1e-10) return null;
  }
  return [Math.max(0, low), Math.min(1, high)] as const;
}
function field(key: string, sources: (SurfaceFrame | TraceTile)[]) {
  const indices = sources.map(sourceIndex),
    cache = new WeakMap<StreetPath, Map<string, FloodRoute>>();
  return {
    key,
    nearest(point: Point, radius: number) {
      let result: { point: [number, number]; contact: FloodContact; distance: number } | null =
        null;
      const a: Point = [point[0] - radius, point[1] - radius];
      const b: Point = [point[0] + radius, point[1] + radius];
      for (const index of indices)
        for (const triangle of index(a, b)) {
          if (triangleIntersection(point, point, triangle.vertices)) {
            return {
              point: [...point] as [number, number],
              contact: this.contact(point) ?? triangle.contact,
              distance: 0,
            };
          }
          for (let i = 0; i < 3; i++) {
            const start = triangle.vertices[i],
              end = triangle.vertices[(i + 1) % 3];
            const dx = end[0] - start[0],
              dy = end[1] - start[1];
            const length2 = dx * dx + dy * dy;
            const t = length2
              ? Math.max(
                  0,
                  Math.min(1, ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / length2)
                )
              : 0;
            const closest: [number, number] = [start[0] + dx * t, start[1] + dy * t];
            const distance = Math.hypot(closest[0] - point[0], closest[1] - point[1]);
            if (distance <= radius && (!result || distance < result.distance))
              result = { point: closest, contact: triangle.contact, distance };
          }
        }
      return result;
    },
    contact(point: Point): FloodContact | null {
      let found: FloodContact | null = null;
      for (const index of indices)
        for (const triangle of index(point, point))
          if (triangleIntersection(point, point, triangle.vertices))
            found = found ? stronger(found, triangle.contact) : triangle.contact;
      return found;
    },
    route(
      path: StreetPath,
      walking: boolean,
      direction: number,
      lane = streetLane(path.road, walking, direction)
    ): FloodRoute {
      const mode = walking + ':' + direction + ':' + lane,
        saved = cache.get(path)?.get(mode);
      if (saved) return saved;
      const bands: FloodBand[] = [];
      // 교량의 실제 노면 표고 없이 지표 수심을 교량 위 피해로 전용하지 않는다.
      if (!path.road.bridge) {
        for (let i = 1; i < path.road.coordinates.length; i++) {
          const length = path.cumulative[i] - path.cumulative[i - 1];
          if (length < 1e-8) continue;
          const a = pathPosition(path, path.cumulative[i - 1], lane, direction),
            b = pathPosition(path, path.cumulative[i], lane, direction);
          const start: Point = [a.x, a.y],
            end: Point = [b.x, b.y];
          for (const index of indices)
            for (const triangle of index(start, end)) {
              const hit = triangleIntersection(start, end, triangle.vertices);
              if (!hit || hit[1] - hit[0] < 1e-10) continue;
              bands.push({
                from: path.cumulative[i - 1] + hit[0] * length,
                to: path.cumulative[i - 1] + hit[1] * length,
                contact: triangle.contact,
              });
            }
        }
      }
      bands.sort((a, b) => a.from - b.from || a.to - b.to);
      const merged: FloodBand[] = [];
      for (const band of bands) {
        const last = merged.at(-1);
        if (last && band.from <= last.to + 1e-6) {
          last.to = Math.max(last.to, band.to);
          last.contact = stronger(last.contact, band.contact);
        } else merged.push({ ...band });
      }
      const value = { length: path.length, bands: merged, samples: bands };
      const modes = cache.get(path) ?? new Map();
      modes.set(mode, value);
      cache.set(path, modes);
      return value;
    },
  };
}
export type FloodField = ReturnType<typeof field>;
export function createFloodField(
  frames: SurfaceFrame[],
  traces: TraceTile[],
  historical: boolean
): FloodField {
  const sources: (SurfaceFrame | TraceTile)[] = [...frames, ...(historical ? traces : [])];
  const key = sources
    .map((source) => {
      if (!identities.has(source)) identities.set(source, ++sequence);
      return identities.get(source);
    })
    .join(':');
  const cached = fields.get(key);
  if (cached) return cached;
  const value = field(key, sources);
  fields.set(key, value);
  while (fields.size > 4) fields.delete(fields.keys().next().value!);
  return value;
}
