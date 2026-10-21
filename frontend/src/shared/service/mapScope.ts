import polygonClipping from 'polygon-clipping';
import { insideRainArea } from '../../domains/rainfall/service/rainEffectService';
export type Point = [number, number];
export type Polygons = Point[][][];
export type Bounds = [number, number, number, number];
export type MapScope = { ids: string[]; polygons: Polygons; bounds: Bounds };
export function polygonBounds(polygons: Polygons): Bounds {
  const bounds: Bounds = [Infinity, Infinity, -Infinity, -Infinity];
  for (const polygon of polygons)
    for (const ring of polygon)
      for (const [x, y] of ring) {
        bounds[0] = Math.min(bounds[0], x);
        bounds[1] = Math.min(bounds[1], y);
        bounds[2] = Math.max(bounds[2], x);
        bounds[3] = Math.max(bounds[3], y);
      }
  return bounds;
}
export function mapScope(districts: { id: string; polygons: Polygons }[]): MapScope {
  const polygons = districts.flatMap((d) => d.polygons);
  return { ids: districts.map((d) => d.id).sort(), polygons, bounds: polygonBounds(polygons) };
}
const overlap = (a: readonly number[], b: readonly number[]) =>
  a[0] <= b[2] && a[2] >= b[0] && a[1] <= b[3] && a[3] >= b[1];
export function clipPolygons(polygons: Polygons, scope?: MapScope): Polygons {
  if (!scope) return polygons;
  if (!polygons.length) return [];
  const bounds = polygonBounds(polygons);
  if (!overlap(bounds, scope.bounds)) return [];
  if (!boundaryEdges(bounds, scope).length)
    return scopeContains(polygons[0][0][0], scope) ? polygons : [];
  return polygonClipping.intersection(polygons, scope.polygons) as Polygons;
}
const tileMatches = new WeakMap<MapScope, Map<string, boolean>>();
export function scopeIntersects(bounds: readonly number[], scope?: MapScope) {
  if (!scope) return true;
  let cache = tileMatches.get(scope);
  if (!cache) {
    cache = new Map();
    tileMatches.set(scope, cache);
  }
  const key = bounds.join(',');
  if (cache.has(key)) return cache.get(key)!;
  const [a, b, c, d] = bounds;
  const value =
    overlap(bounds, scope.bounds) &&
    ((
      [
        [a, b],
        [c, b],
        [c, d],
        [a, d],
      ] as Point[]
    ).some((p) => scopeContains(p, scope)) ||
      boundaryEdges([a, b, c, d], scope).some((edge) => {
        let lo = 0,
          hi = 1;
        for (let axis = 0; axis < 2; axis++) {
          const delta = edge.b[axis] - edge.a[axis],
            start = edge.a[axis];
          if (delta === 0) {
            if (start < bounds[axis] || start > bounds[axis + 2]) return false;
            continue;
          }
          const t0 = (bounds[axis] - start) / delta,
            t1 = (bounds[axis + 2] - start) / delta;
          lo = Math.max(lo, Math.min(t0, t1));
          hi = Math.min(hi, Math.max(t0, t1));
          if (lo > hi) return false;
        }
        return true;
      }));
  cache.set(key, value);
  return value;
}
export function scopeContains(point: Point, scope?: MapScope) {
  return !scope || insideRainArea(point, scope.polygons);
}
type Edge = { a: Point; b: Point; bounds: Bounds };
const edgeIndexes = new WeakMap<MapScope, { all: Edge[]; cells: Map<string, Edge[]> }>();
export function boundaryEdges(bounds: Bounds, scope: MapScope): Edge[] {
  let index = edgeIndexes.get(scope);
  if (!index) {
    const all: Edge[] = [],
      cells = new Map<string, Edge[]>();
    for (const polygon of scope.polygons)
      for (const ring of polygon)
        for (let i = 1; i < ring.length; i++) {
          const a = ring[i - 1],
            b = ring[i],
            edge: Edge = {
              a,
              b,
              bounds: [
                Math.min(a[0], b[0]),
                Math.min(a[1], b[1]),
                Math.max(a[0], b[0]),
                Math.max(a[1], b[1]),
              ],
            };
          all.push(edge);
          for (let x = Math.floor(edge.bounds[0] / 250); x <= Math.floor(edge.bounds[2] / 250); x++)
            for (
              let y = Math.floor(edge.bounds[1] / 250);
              y <= Math.floor(edge.bounds[3] / 250);
              y++
            ) {
              const key = x + ',' + y,
                list = cells.get(key) ?? [];
              list.push(edge);
              cells.set(key, list);
            }
        }
    index = { all, cells };
    edgeIndexes.set(scope, index);
  }
  const x0 = Math.floor(bounds[0] / 250),
    x1 = Math.floor(bounds[2] / 250),
    y0 = Math.floor(bounds[1] / 250),
    y1 = Math.floor(bounds[3] / 250);
  if ((x1 - x0 + 1) * (y1 - y0 + 1) > 10000)
    return index.all.filter((e) => overlap(e.bounds, bounds));
  const result = new Set<Edge>();
  for (let x = x0; x <= x1; x++)
    for (let y = y0; y <= y1; y++)
      for (const edge of index.cells.get(x + ',' + y) ?? [])
        if (overlap(edge.bounds, bounds)) result.add(edge);
  return [...result];
}
// 표시 선만 행정 경계에서 자르며 원본 좌표·설치 후보·물리 입력은 바꾸지 않는다.
export function clipLine(line: Point[], scope?: MapScope): Point[][] {
  if (!scope) return [line];
  const result: Point[][] = [];
  for (let i = 1; i < line.length; i++) {
    const a = line[i - 1],
      b = line[i],
      dx = b[0] - a[0],
      dy = b[1] - a[1],
      cuts = [0, 1];
    for (const { a: c, b: d } of boundaryEdges(
      [Math.min(a[0], b[0]), Math.min(a[1], b[1]), Math.max(a[0], b[0]), Math.max(a[1], b[1])],
      scope
    )) {
      const ex = d[0] - c[0],
        ey = d[1] - c[1],
        cross = dx * ey - dy * ex;
      if (Math.abs(cross) < 1e-12) continue;
      const t = ((c[0] - a[0]) * ey - (c[1] - a[1]) * ex) / cross;
      const u = ((c[0] - a[0]) * dy - (c[1] - a[1]) * dx) / cross;
      if (t > 0 && t < 1 && u >= 0 && u <= 1) cuts.push(t);
    }
    cuts.sort((x, y) => x - y);
    for (let j = 1; j < cuts.length; j++) {
      const first = cuts[j - 1],
        last = cuts[j];
      if (
        last - first < 1e-10 ||
        !scopeContains([a[0] + (dx * (first + last)) / 2, a[1] + (dy * (first + last)) / 2], scope)
      )
        continue;
      const from: Point = [a[0] + dx * first, a[1] + dy * first],
        to: Point = [a[0] + dx * last, a[1] + dy * last];
      const previous = result.at(-1),
        end = previous?.at(-1);
      if (end && Math.hypot(end[0] - from[0], end[1] - from[1]) < 1e-7) previous!.push(to);
      else result.push([from, to]);
    }
  }
  return result;
}
