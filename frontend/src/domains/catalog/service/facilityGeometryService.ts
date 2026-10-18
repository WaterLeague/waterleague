import { ShapeUtils } from 'three/src/extras/ShapeUtils.js';
import { Vector2 } from 'three/src/math/Vector2.js';
import type { FacilityFootprint, MapPoint } from '../entity/facilityFootprint';
import { CatalogError } from '../exception/CatalogError';
import type { SwaleDesign } from '../../facility/dto/facilityDto';
import type { Placement } from '../../game/entity/game';

export function placementFootprint(
  cell: { coordinates: MapPoint[]; areaM2: number; physicalInputs?: { swaleDesign?: SwaleDesign } },
  placement: Placement
) {
  if (placement.facilityType !== 'VEGETATIVE_SWALE')
    return facilityFootprint(cell.coordinates, placement.areaM2 / cell.areaM2);
  const d = cell.physicalInputs?.swaleDesign;
  if (
    !d ||
    !Number.isFinite(placement.areaM2) ||
    placement.areaM2 <= 0 ||
    placement.areaM2 > d.maxAreaM2
  )
    throw new CatalogError('INVALID_DATA');
  const [dx, dy] = d.direction;
  const halfLength = placement.areaM2 / d.topWidthM / 2;
  const points = [
    [-1, -1],
    [1, -1],
    [1, 1],
    [-1, 1],
  ].map(([s, t]): MapPoint => [
    d.center[0] + dx * s * halfLength - (dy * t * d.topWidthM) / 2,
    d.center[1] + dy * s * halfLength + (dx * t * d.topWidthM) / 2,
  ]);
  return facilityFootprint(points, 1);
}

const epsilon = 1e-8;
const cross = (a: MapPoint, b: MapPoint, c: MapPoint) =>
  (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]);
const same = (a: MapPoint, b: MapPoint) => a[0] === b[0] && a[1] === b[1];
const onSegment = (a: MapPoint, b: MapPoint, p: MapPoint) =>
  Math.abs(cross(a, b, p)) <= epsilon &&
  p.every(
    (value, axis) =>
      value >= Math.min(a[axis], b[axis]) - epsilon && value <= Math.max(a[axis], b[axis]) + epsilon
  );

export function polygonArea(points: MapPoint[]): number {
  return (
    Math.abs(
      points.reduce((sum, point, i) => {
        const next = points[(i + 1) % points.length];
        return sum + point[0] * next[1] - next[0] * point[1];
      }, 0)
    ) / 2
  );
}

function intersects(a: MapPoint, b: MapPoint, c: MapPoint, d: MapPoint) {
  return (
    onSegment(a, b, c) ||
    onSegment(a, b, d) ||
    onSegment(c, d, a) ||
    onSegment(c, d, b) ||
    (cross(a, b, c) * cross(a, b, d) < 0 && cross(c, d, a) * cross(c, d, b) < 0)
  );
}

function clip(points: MapPoint[], axis: number, cutoff: number): MapPoint[] {
  const result: MapPoint[] = [];
  for (let i = 0; i < points.length; i++) {
    const a = points[i],
      b = points[(i + 1) % points.length];
    const aInside = a[axis] <= cutoff,
      bInside = b[axis] <= cutoff;
    if (aInside) result.push(a);
    if (aInside !== bInside) {
      const t = (cutoff - a[axis]) / (b[axis] - a[axis]);
      result.push([a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])]);
    }
  }
  return result.filter((p, i) => !same(p, result[(i + 1) % result.length]));
}

export function facilityFootprint(coordinates: MapPoint[], ratio: number): FacilityFootprint {
  if (
    !Number.isFinite(ratio) ||
    ratio <= 0 ||
    ratio > 1 ||
    coordinates.length < 3 ||
    coordinates.length > 500 ||
    coordinates.some((p) => p.length !== 2 || p.some((n) => !Number.isFinite(n)))
  )
    throw new CatalogError('INVALID_DATA');
  const points = coordinates.map((p): MapPoint => [...p]);
  if (same(points[0], points[points.length - 1])) points.pop();
  const originalArea = polygonArea(points);
  if (points.length < 3 || !Number.isFinite(originalArea) || originalArea * ratio <= epsilon)
    throw new CatalogError('INVALID_DATA');
  for (let i = 0; i < points.length; i++) {
    const a = points[i],
      b = points[(i + 1) % points.length];
    if (same(a, b)) throw new CatalogError('INVALID_DATA');
    for (let j = i + 1; j < points.length; j++) {
      if (j === i + 1 || (i === 0 && j === points.length - 1)) continue;
      if (intersects(a, b, points[j], points[(j + 1) % points.length]))
        throw new CatalogError('INVALID_DATA');
    }
  }
  const triangles = ShapeUtils.triangulateShape(
    points.map(([x, y]) => new Vector2(x, y)),
    []
  ).map((ids) => {
    const triangle = ids.map((id) => points[id]);
    if (cross(triangle[0], triangle[1], triangle[2]) < 0) triangle.reverse();
    return triangle;
  });
  if (
    Math.abs(triangles.reduce((sum, t) => sum + polygonArea(t), 0) - originalArea) >
    Math.max(epsilon, originalArea * 1e-9)
  )
    throw new CatalogError('INVALID_DATA');
  const min = [0, 1].map((axis) => Math.min(...points.map((p) => p[axis])));
  const max = [0, 1].map((axis) => Math.max(...points.map((p) => p[axis])));
  const axis = max[0] - min[0] >= max[1] - min[1] ? 0 : 1;
  let low = min[axis],
    high = max[axis];
  // 모든 삼각형에 같은 절단선을 적용해 면적 비율과 구역 경계를 함께 보존한다.
  for (let i = 0; i < 52 && ratio < 1; i++) {
    const middle = (low + high) / 2;
    const area = triangles.reduce((sum, t) => sum + polygonArea(clip(t, axis, middle)), 0);
    if (area < originalArea * ratio) low = middle;
    else high = middle;
  }
  const polygons = (
    ratio === 1 ? triangles : triangles.map((t) => clip(t, axis, (low + high) / 2))
  ).filter((p) => p.length >= 3 && polygonArea(p) > epsilon);
  const edges = new Map<string, [MapPoint, MapPoint]>();
  const key = (p: MapPoint) => p.map((n) => Math.round(n * 1e7)).join(',');
  for (const polygon of polygons)
    for (let i = 0; i < polygon.length; i++) {
      const a = polygon[i],
        b = polygon[(i + 1) % polygon.length];
      const edgeKey = [key(a), key(b)].sort().join('|');
      if (edges.has(edgeKey)) edges.delete(edgeKey);
      else edges.set(edgeKey, [a, b]);
    }
  return {
    polygons,
    boundary: [...edges.values()],
    area: polygons.reduce((sum, p) => sum + polygonArea(p), 0),
  };
}

export function plantingMarkers(footprint: FacilityFootprint, limit = 48): MapPoint[] {
  if (!Number.isInteger(limit) || limit < 1 || limit > 64) throw new CatalogError('INVALID_DATA');
  const points = footprint.polygons.flat();
  if (!points.length) return [];
  const min = [0, 1].map((axis) => Math.min(...points.map((p) => p[axis])));
  const max = [0, 1].map((axis) => Math.max(...points.map((p) => p[axis])));
  const step = Math.max(2.4, Math.sqrt(((max[0] - min[0]) * (max[1] - min[1])) / limit));
  const result: MapPoint[] = [];
  for (let y = min[1] + step / 2; y < max[1] && result.length < limit; y += step)
    for (let x = min[0] + step / 2; x < max[0] && result.length < limit; x += step) {
      const point: MapPoint = [x, y];
      if (
        !footprint.polygons.some((p) =>
          p.every((a, i) => cross(a, p[(i + 1) % p.length], point) >= -epsilon)
        )
      )
        continue;
      const clearance = footprint.boundary.every(([a, b]) => {
        const dx = b[0] - a[0],
          dy = b[1] - a[1];
        const t = Math.max(
          0,
          Math.min(1, ((x - a[0]) * dx + (y - a[1]) * dy) / (dx * dx + dy * dy))
        );
        return Math.hypot(x - a[0] - t * dx, y - a[1] - t * dy) >= 0.8;
      });
      if (clearance) result.push(point);
    }
  return result;
}
