import { Color, ShapeUtils, Vector2 } from 'three';
import type { Street } from '../entity/urban';
import type { Terrain } from '../../terrain/entity/terrain';
import { drapeTriangle, terrainMeshHeight } from '../../terrain/service/terrainDrapeService';
import { pathPosition, streetPath, sidewalkSides } from './streetLifeService';
type Point = [number, number];
// 실측 제원이 없는 교량은 공개 층·연결 관계를 보존한 표시 높이를 사용한다.
export const bridgeDeckHeight = 6.5;
export const bridgeDeckThickness = 0.65;
export function streetHeight(
  terrain: Terrain | null,
  point: readonly [number, number],
  road: boolean | Street,
  segment?: number
) {
  if (typeof road === 'object' && road.elevationsM) {
    let nearest = Infinity,
      height = 0;
    const first = segment ?? 0,
      last = segment === undefined ? road.coordinates.length - 1 : segment + 1;
    for (let i = first; i < last; i++) {
      const a = road.coordinates[i],
        b = road.coordinates[i + 1],
        dx = b[0] - a[0],
        dy = b[1] - a[1];
      const t = Math.max(
        0,
        Math.min(1, ((point[0] - a[0]) * dx + (point[1] - a[1]) * dy) / (dx * dx + dy * dy || 1))
      );
      const distance = (point[0] - a[0] - dx * t) ** 2 + (point[1] - a[1] - dy * t) ** 2;
      if (distance < nearest) {
        nearest = distance;
        height = road.elevationsM[i] * (1 - t) + road.elevationsM[i + 1] * t;
      }
    }
    return height + 0.004;
  }
  return (
    terrainMeshHeight(terrain, point) +
    ((typeof road === 'boolean' ? road : road.bridge) ? bridgeDeckHeight : 0.004)
  );
}
export { hasInlineSidewalk } from './streetLifeService';
// 같은 꼭짓점의 법선을 공유해 꺾이는 도로에 틈과 중복 사각형이 생기지 않게 한다.
export function streetOffsets(points: Point[], offset: number): Point[] {
  const normal = (a: Point, b: Point): Point => {
    const d = Math.hypot(b[0] - a[0], b[1] - a[1]) || 1;
    return [-(b[1] - a[1]) / d, (b[0] - a[0]) / d];
  };
  return points.map((p, i) => {
    const a = normal(points[Math.max(0, i - 1)], points[i === 0 ? 1 : i]);
    const b = normal(
      points[i === points.length - 1 ? i - 1 : i],
      points[Math.min(points.length - 1, i + 1)]
    );
    const sx = a[0] + b[0],
      sy = a[1] + b[1],
      len = Math.hypot(sx, sy) || 1,
      mx = sx / len,
      my = sy / len;
    const scale =
      Math.min(Math.abs(offset) * 2.5, Math.abs(offset) / Math.max(0.2, mx * b[0] + my * b[1])) *
      Math.sign(offset);
    return [p[0] + mx * scale, p[1] + my * scale];
  });
}
export function streetGeometry(
  roads: Street[],
  terrain: Terrain | null,
  detail: boolean,
  parkingAisles: string[] = []
) {
  const positions: number[] = [],
    colors: number[] = [],
    ends: number[] = [];
  const asphalt = new Color('#667071'),
    walk = new Color('#b3ae9f'),
    paint = new Color('#e8e5d4'),
    concrete = new Color('#99a7a6'),
    barrier = new Color('#b6c8c5'),
    underside = new Color('#58656d'),
    aisle = new Color('#747b76'),
    arch = new Color('#b7c9b7');
  const aisleIds = new Set(parkingAisles);
  const face = (a: number[], b: number[], c: number[], color: Color) => {
    for (const p of [a, b, c]) {
      positions.push(p[0], p[1], -p[2]);
      colors.push(color.r, color.g, color.b);
    }
  };
  for (const road of roads) {
    const path = streetPath(road),
      parking = aisleIds.has(road.id),
      crossing = road.footway === 'crossing';
    const height = (p: readonly [number, number], segment?: number) =>
      streetHeight(terrain, p, road, segment);
    const triangle = (
      points: [Point, Point, Point],
      color: Color,
      lift: number,
      segment?: number
    ) => {
      const emit = (t: readonly (readonly [number, number])[]) => {
        for (const p of t) {
          positions.push(p[0], height(p, segment) + lift, -p[1]);
          colors.push(color.r, color.g, color.b);
        }
      };
      if (road.elevationsM || road.bridge) emit(points);
      else drapeTriangle(points, terrain, emit);
    };
    const strip = (left: Point[], right: Point[], color: Color, lift: number) => {
      for (let i = 1; i < left.length; i++) {
        triangle([left[i - 1], right[i - 1], left[i]], color, lift, i - 1);
        triangle([left[i], right[i - 1], right[i]], color, lift, i - 1);
      }
    };
    const mark = (start: number, end: number, width: number, offset = 0) => {
      const a = pathPosition(path, start, offset, 1),
        b = pathPosition(path, end, offset, 1),
        points: [Point, Point] = [
          [a.x, a.y],
          [b.x, b.y],
        ];
      strip(streetOffsets(points, width / 2), streetOffsets(points, -width / 2), paint, 0.008);
    };
    const beam = (a: number[], b: number[], width: number, depth: number, color: Color) => {
      const dx = b[0] - a[0],
        dy = b[1] - a[1],
        dz = b[2] - a[2],
        length = Math.hypot(dx, dy, dz);
      if (length < 0.0001) return;
      const horizontal = Math.hypot(dx, dz),
        nx = horizontal ? -dz / horizontal : 1,
        nz = horizontal ? dx / horizontal : 0;
      const ux = (dy / length) * nz,
        uy = (dz * nx - dx * nz) / length,
        uz = (-dy / length) * nx;
      const corners = (p: number[]) =>
        [
          [1, -1],
          [-1, -1],
          [-1, 1],
          [1, 1],
        ].map(([side, up]) => [
          p[0] + ((nx * width) / 2) * side + ((ux * depth) / 2) * up,
          p[1] + ((uy * depth) / 2) * up,
          p[2] + ((nz * width) / 2) * side + ((uz * depth) / 2) * up,
        ]);
      const v = [...corners(a), ...corners(b)];
      for (const q of [
        [0, 1, 2, 3],
        [4, 7, 6, 5],
        [0, 4, 5, 1],
        [3, 2, 6, 7],
        [0, 3, 7, 4],
        [1, 5, 6, 2],
      ]) {
        face(v[q[0]], v[q[1]], v[q[2]], color);
        face(v[q[0]], v[q[2]], v[q[3]], color);
      }
    };
    const left = streetOffsets(road.coordinates, road.widthM / 2),
      right = streetOffsets(road.coordinates, -road.widthM / 2);
    if (!crossing) {
      if (road.walkPolygons) {
        for (const polygon of road.walkPolygons) {
          const rings = polygon.map((r) => r.slice(0, -1).map((p) => new Vector2(...p))),
            points = rings.flat();
          for (const f of ShapeUtils.triangulateShape(rings[0], rings.slice(1)))
            triangle(
              f.map((i) => [points[i].x, points[i].y]) as [Point, Point, Point],
              walk,
              0.004
            );
        }
      } else strip(left, right, road.walk ? walk : parking ? aisle : asphalt, 0.004);
      if (detail && !parking && road.motor && !/motorway|trunk/.test(road.class)) {
        const [l, r] = sidewalkSides(road);
        if (l) strip(streetOffsets(road.coordinates, road.widthM / 2 + 1.4), left, walk, 0);
        if (r) strip(right, streetOffsets(road.coordinates, -road.widthM / 2 - 1.4), walk, 0);
      }
    } else if (detail && road.crossing !== 'unmarked' && road.crossing !== 'no') {
      // 횡단보도 태그가 있는 보행 선에만 노면 표식을 그린다.
      for (let s = 0.3; s < path.length; s += 1.2)
        mark(s, Math.min(path.length, s + 0.5), Math.max(2, road.widthM));
    }
    if (detail && !parking && road.motor && road.widthM >= 6) {
      const lanes = road.lanes ?? Math.max(1, Math.round(road.widthM / 3.5));
      const start = road.junctionStartM ?? 0,
        end = path.length - (road.junctionEndM ?? 0);
      for (let lane = 1; lane < lanes; lane++)
        for (let s = Math.ceil(start / 12) * 12; s < end; s += 12)
          mark(s, Math.min(end, s + 4), 0.15, (lane / lanes - 0.5) * road.widthM);
    }
    if (detail && road.class === 'steps')
      for (let s = 0; s < path.length; s += 0.4)
        mark(s, Math.min(path.length, s + 0.07), road.widthM);
    if (detail && road.bridge) {
      strip(left, right, underside, -bridgeDeckThickness);
      for (const edge of [left, right])
        for (let i = 1; i < edge.length; i++) {
          const a = edge[i - 1],
            b = edge[i],
            ha = height(a, i - 1),
            hb = height(b, i - 1);
          face(
            [a[0], ha - bridgeDeckThickness, a[1]],
            [b[0], hb - bridgeDeckThickness, b[1]],
            [a[0], ha, a[1]],
            concrete
          );
          face(
            [b[0], hb - bridgeDeckThickness, b[1]],
            [b[0], hb, b[1]],
            [a[0], ha, a[1]],
            concrete
          );
          beam([a[0], ha + 0.9, a[1]], [b[0], hb + 0.9, b[1]], 0.12, 0.12, barrier);
        }
      for (let s = 0; s < path.length; s += 4)
        for (const side of [-1, 1]) {
          const p = pathPosition(path, s, (side * road.widthM) / 2, 1),
            h = height([p.x, p.y], p.segment);
          beam([p.x, h, p.y], [p.x, h + 0.9, p.y], 0.12, 0.12, barrier);
        }
      if (road.elevationsM) {
        const spans = Math.max(1, Math.round(path.length / 65)),
          span = path.length / spans;
        for (let j = 1; j < spans; j++) {
          const p = pathPosition(path, j * span, 0, 1),
            deck = height([p.x, p.y], p.segment),
            ground = terrainMeshHeight(terrain, [p.x, p.y]);
          if (deck - ground > 4) {
            // 교각 간격·폭은 구조 실측이 아닌 상판 지지의 표시 제원이다.
            const angle = p.angle,
              across: [number, number] = [Math.cos(angle), Math.sin(angle)];
            for (const side of [-1, 1]) {
              const x = p.x + across[0] * road.widthM * 0.28 * side,
                y = p.y - across[1] * road.widthM * 0.28 * side;
              beam([x, ground, y], [x, deck - bridgeDeckThickness, y], 1.4, 1.4, concrete);
            }
          }
        }
        if (road.structure === 'arch' && road.motor && path.length > 50) {
          for (let j = 0; j < spans; j++)
            for (const side of [-1, 1]) {
              let previous: number[] | null = null;
              for (let k = 0; k <= 20; k++) {
                const t = k / 20,
                  p = pathPosition(path, (j + t) * span, side * (road.widthM / 2 + 0.3), 1),
                  h = height([p.x, p.y], p.segment),
                  lift = Math.sin(Math.PI * t) * Math.min(13, span * 0.19),
                  point = [p.x, h + lift, p.y];
                if (previous) beam(previous, point, 0.6, 0.7, arch);
                if (k > 0 && k < 20 && k % 2 === 0) beam([p.x, h, p.y], point, 0.14, 0.14, barrier);
                previous = point;
              }
            }
        }
      }
    }
    ends.push(positions.length / 9);
    if (positions.length > 18000000) throw new Error('도로 표시 형상 상한 초과');
  }
  return { positions: new Float32Array(positions), colors: new Float32Array(colors), ends };
}
export function streetAtFace(ends: readonly number[], face: number) {
  if (!Number.isInteger(face) || face < 0 || face >= (ends.at(-1) ?? 0)) return -1;
  let low = 0,
    high = ends.length;
  while (low < high) {
    const mid = (low + high) >>> 1;
    if (face < ends[mid]) high = mid;
    else low = mid + 1;
  }
  return low;
}
