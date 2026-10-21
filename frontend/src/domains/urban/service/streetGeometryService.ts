import { bridgeAxis, bridgePierPositions } from './nativeBridgeStructureService';
import { bridgeArchitecture } from './bridgeArchitectureService';
import { stairTriangles } from '../../../shared/service/polygonBandService';
import { nativeSurfaceColor } from './nativeStreetService';
import { nativeBridgeHeight, nativeBridgeProfileHeight, withinBridge } from './nativeBridgeService';
import { bridgeTransportHeight } from './nativeBridgeTransportService';
import { NativeGroundCuts } from './nativeGroundCutService';
import { Color, ShapeUtils, Vector2 } from 'three';
import type { Street } from '../entity/urban';
import type { Terrain } from '../../terrain/entity/terrain';
import {
  drapeTriangle,
  drapeSegment,
  terrainMeshHeight,
} from '../../terrain/service/terrainDrapeService';
import { pathPosition, streetPath, sidewalkSides } from './streetLifeService';
type Point = [number, number];
const waterMasks = new WeakMap<object, NativeGroundCuts>();
export function submergedSourcePath(road: Street, terrain: Terrain | null, point: Point) {
  const polygons = road.nativeGroundCutPolygons;
  if (
    !polygons?.length ||
    streetHeight(terrain, point, road) > terrainMeshHeight(terrain, point) + 0.25
  )
    return false;
  let mask = waterMasks.get(polygons);
  if (!mask) {
    mask = new NativeGroundCuts([], polygons);
    waterMasks.set(polygons, mask);
  }
  return mask.contains(point);
}
// 실측 제원이 없는 교량은 공개 층·연결 관계를 보존한 표시 높이를 사용한다.
export const bridgeDeckHeight = 6.5;
export const bridgeDeckThickness = 0.65;
export function streetHeight(
  terrain: Terrain | null,
  point: readonly [number, number],
  road: boolean | Street,
  segment?: number
) {
  if (typeof road === 'object' && road.nativeWaterDecks?.length) {
    const decks = road.nativeWaterDecks.filter(
      (d) => withinBridge(point, d.polygons) && withinBridge(point, d.waterPolygons)
    );
    if (decks.length)
      return (
        Math.max(...decks.map((d) => nativeBridgeHeight(terrain, d.deckPolygons, d.deckLiftM))) +
        (road.walk ? 0.14 : 0.016)
      );
  }
  if (typeof road === 'object' && road.nativeWalkingDecks)
    for (const deck of road.nativeWalkingDecks)
      if (withinBridge(point, deck.polygons))
        return (
          (deck.profile
            ? nativeBridgeProfileHeight(terrain, point, deck.profile)
            : nativeBridgeHeight(terrain, deck.deckPolygons, deck.deckLiftM)) + 0.14
        );
  if (typeof road === 'object' && road.nativeRailKind)
    return (
      (bridgeTransportHeight(road.nativeBridgeProfiles, terrain)?.(point) ??
        terrainMeshHeight(terrain, point)) + 0.016
    );
  if (typeof road === 'object' && road.nativeBridgeProfiles?.length)
    return (
      Math.max(
        ...road.nativeBridgeProfiles.map((profile) =>
          nativeBridgeProfileHeight(terrain, point, profile)
        )
      ) + (road.nativeSourceRole === 'SIDEWALK_AREA' ? 0.14 : 0.016)
    );
  if (typeof road === 'object' && road.bridge && road.nativePolygons)
    return (
      nativeBridgeHeight(
        terrain,
        road.nativeBridgeGroupPolygons ?? road.nativePolygons,
        road.nativeDeckLiftM
      ) + (road.nativeSourceRole === 'SIDEWALK_AREA' ? 0.14 : 0.016)
    );
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
export function streetDetailEnabled(
  road: Street,
  detailed: boolean,
  detailCenter?: Point
): boolean {
  return (
    detailed &&
    (!detailCenter ||
      road.coordinates.some((p, i) => {
        const q = road.coordinates[Math.max(0, i - 1)];
        const dx = p[0] - q[0],
          dy = p[1] - q[1];
        const t = Math.max(
          0,
          Math.min(
            1,
            ((detailCenter[0] - q[0]) * dx + (detailCenter[1] - q[1]) * dy) /
              (dx * dx + dy * dy || 1)
          )
        );
        return Math.hypot(q[0] + dx * t - detailCenter[0], q[1] + dy * t - detailCenter[1]) < 1400;
      }))
  );
}
export function streetGeometry(
  roads: Street[],
  terrain: Terrain | null,
  detailed: boolean,
  parkingAisles: string[] = [],
  detailCenter?: Point
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
  for (const road of roads) {
    const detail = streetDetailEnabled(road, detailed, detailCenter);
    if (road.nativeSourceRole) {
      const bridgeHeight =
        road.bridge && road.nativePolygons && !road.nativeBridgeProfiles?.length
          ? nativeBridgeHeight(
              terrain,
              road.nativeBridgeGroupPolygons ?? road.nativePolygons,
              road.nativeDeckLiftM
            )
          : null;
      const marking = road.nativeMarkingPolygons;
      const surfaceLift = road.nativeSourceRole === 'SIDEWALK_AREA' ? 0.14 : 0.016;
      const slabThickness = road.nativeSourceRole === 'SIDEWALK_AREA' ? 0.124 : bridgeDeckThickness;
      if (bridgeHeight !== null) bridgeArchitecture(road, bridgeHeight + 0.016, beam, detail);
      if (marking ? detail : road.nativePolygons)
        for (const component of marking ?? road.nativePolygons ?? []) {
          const rings = component.map((ring) =>
            ring.slice(0, -1).map(([x, y]) => new Vector2(x, y))
          );
          const points = rings.flat();
          const color = marking ? paint : new Color(nativeSurfaceColor(road.nativeSourceRole));
          for (const ids of ShapeUtils.triangulateShape(rings[0], rings.slice(1))) {
            const triangle = ids.map((id) => [points[id].x, points[id].y] as Point) as [
              Point,
              Point,
              Point,
            ];
            const emit = (part: readonly (readonly [number, number])[]) => {
              for (const p of part) {
                positions.push(
                  p[0],
                  (road.nativeBridgeProfiles?.length
                    ? streetHeight(terrain, p, road) - surfaceLift
                    : (bridgeHeight ?? terrainMeshHeight(terrain, p))) +
                    (marking ? 0.055 : surfaceLift),
                  -p[1]
                );
                colors.push(color.r, color.g, color.b);
              }
              if (road.nativeBridgeProfiles?.length && !road.nativeBridgeProfiles[0].steps) {
                const bottom = part.map((p) => [
                  p[0],
                  Math.max(
                    terrainMeshHeight(terrain, p),
                    streetHeight(terrain, p, road) - slabThickness
                  ),
                  p[1],
                ]);
                face(bottom[0], bottom[2], bottom[1], underside);
              }
            };
            const profile = road.nativeBridgeProfiles?.[0];
            if (profile?.steps && detail) {
              const a = profile.coordinates[0],
                b = profile.coordinates.at(-1)!,
                dx = b[0] - a[0],
                dy = b[1] - a[1],
                length = Math.hypot(dx, dy),
                axis: Point = [dx / length, dy / length],
                origin = a[0] * axis[0] + a[1] * axis[1],
                step = length / Math.max(1, Math.ceil(length / 0.32));
              for (const section of stairTriangles(triangle, axis, origin, step)) {
                const middle = Math.min(length, (section.band + 0.5) * step),
                  height =
                    nativeBridgeProfileHeight(
                      terrain,
                      [a[0] + axis[0] * middle, a[1] + axis[1] * middle],
                      profile
                    ) + 0.016;
                for (let i = 1; i < section.points.length - 1; i++)
                  face(
                    [section.points[0][0], height, section.points[0][1]],
                    [section.points[i][0], height, section.points[i][1]],
                    [section.points[i + 1][0], height, section.points[i + 1][1]],
                    color
                  );
                for (let i = 0; i < section.points.length; i++) {
                  const p = section.points[i],
                    q = section.points[(i + 1) % section.points.length],
                    low = Math.max(terrainMeshHeight(terrain, p), height - bridgeDeckThickness);
                  face([p[0], low, p[1]], [q[0], low, q[1]], [q[0], height, q[1]], color);
                  face([p[0], low, p[1]], [q[0], height, q[1]], [p[0], height, p[1]], color);
                }
              }
            } else if (profile) {
              const split = (t: [Point, Point, Point], depth = 0) => {
                const lengths = t.map((p, i) =>
                    Math.hypot(p[0] - t[(i + 1) % 3][0], p[1] - t[(i + 1) % 3][1])
                  ),
                  longest = Math.max(...lengths),
                  i = lengths.indexOf(longest);
                if (longest <= (detail ? 5 : 40) || depth >= 14) {
                  emit(t);
                  return;
                }
                const a = t[i],
                  b = t[(i + 1) % 3],
                  c = t[(i + 2) % 3],
                  mid: Point = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
                split([a, mid, c], depth + 1);
                split([mid, b, c], depth + 1);
              };
              drapeTriangle(triangle, terrain, (t) =>
                split(t.map((p) => [p[0], p[1]]) as [Point, Point, Point])
              );
            } else if (bridgeHeight !== null) {
              emit(triangle);
              const bottom = triangle.map((p) => [
                p[0],
                bridgeHeight + surfaceLift - slabThickness,
                p[1],
              ]);
              face(bottom[0], bottom[2], bottom[1], underside);
            } else drapeTriangle(triangle, terrain, emit);
          }
          if (
            road.nativeSourceRole === 'SIDEWALK_AREA' &&
            !marking &&
            bridgeHeight === null &&
            !road.nativeBridgeProfiles?.length
          )
            for (const ring of component)
              for (let i = 1; i < ring.length; i++)
                for (const [a, b] of drapeSegment(ring[i - 1], ring[i], terrain)) {
                  const ha = terrainMeshHeight(terrain, a),
                    hb = terrainMeshHeight(terrain, b);
                  face([a[0], ha, a[1]], [b[0], hb, b[1]], [b[0], hb + 0.14, b[1]], walk);
                  face([a[0], ha, a[1]], [b[0], hb + 0.14, b[1]], [a[0], ha + 0.14, a[1]], walk);
                }
          if (road.nativeBridgeProfiles?.length)
            for (const ring of component)
              for (let i = 1; i < ring.length; i++)
                for (const [a, b] of drapeSegment(ring[i - 1], ring[i], terrain)) {
                  const ha = streetHeight(terrain, a, road),
                    hb = streetHeight(terrain, b, road),
                    ga = Math.max(terrainMeshHeight(terrain, a), ha - bridgeDeckThickness),
                    gb = Math.max(terrainMeshHeight(terrain, b), hb - bridgeDeckThickness);
                  face([a[0], ga, a[1]], [b[0], gb, b[1]], [b[0], hb, b[1]], concrete);
                  face([a[0], ga, a[1]], [b[0], hb, b[1]], [a[0], ha, a[1]], concrete);
                }
          if (bridgeHeight !== null)
            for (const ring of component)
              for (let i = 1; i < ring.length; i++) {
                const a = ring[i - 1],
                  b = ring[i],
                  top = bridgeHeight + surfaceLift,
                  bottom = top - slabThickness;
                face([a[0], top, a[1]], [b[0], top, b[1]], [a[0], bottom, a[1]], concrete);
                face([a[0], bottom, a[1]], [b[0], top, b[1]], [b[0], bottom, b[1]], concrete);
              }
          if (detail && road.bridge && road.nativeSourceRole !== 'SIDEWALK_AREA') {
            const axis = bridgeAxis(road.nativePolygons!);
            const top = (p: Point) =>
              bridgeHeight === null ? streetHeight(terrain, p, road) : bridgeHeight + 0.016;
            for (const ring of component)
              for (let i = 1; i < ring.length; i++) {
                const a = ring[i - 1],
                  b = ring[i],
                  dx = b[0] - a[0],
                  dy = b[1] - a[1],
                  length = Math.hypot(dx, dy);
                // 차량·보행 진출입 끝면을 막지 않고 상판 양옆에 표시 난간을 둔다.
                if (length < 0.1 || Math.abs((dx * axis[0] + dy * axis[1]) / length) < 0.5)
                  continue;
                for (const h of [0.5, 1.0])
                  beam([a[0], top(a) + h, a[1]], [b[0], top(b) + h, b[1]], 0.07, 0.07, barrier);
                for (let offset = 0; offset < length; offset += 6) {
                  const t = offset / length,
                    point: Point = [a[0] + dx * t, a[1] + dy * t],
                    height = top(point);
                  beam(
                    [point[0], height, point[1]],
                    [point[0], height + 1.0, point[1]],
                    0.08,
                    0.08,
                    barrier
                  );
                }
              }
          }
        }
      if (detail && road.bridge && road.nativePolygons && road.nativeSourceRole !== 'SIDEWALK_AREA')
        for (const p of bridgePierPositions(
          road.nativePolygons,
          road.nativeDeckLevel === 'upper'
        )) {
          const low = terrainMeshHeight(terrain, p),
            high =
              (bridgeHeight === null ? streetHeight(terrain, p, road) : bridgeHeight + 0.016) -
              bridgeDeckThickness;
          if (high - low >= 2) beam([p[0], low, p[1]], [p[0], high, p[1]], 1.4, 1.4, concrete);
        }
      if (detail)
        for (const lane of road.nativeLanePaths ?? []) {
          const path = streetPath({ ...road, coordinates: lane.coordinates });
          // 차로 수는 원본 속성, 도색 폭·간격은 표시 제원이다.
          for (let divider = 1; divider < lane.lanes; divider++) {
            const offset = (divider / lane.lanes - 0.5) * Math.max(0, lane.widthM - 1);
            for (let s = lane.span[0]; s < lane.span[1]; s += 12) {
              const a = pathPosition(path, s, offset, 1),
                b = pathPosition(path, Math.min(s + 4, lane.span[1]), offset, 1);
              if (
                road.nativeGroundCutPolygons &&
                !road.nativeLaneClipPolygons &&
                (withinBridge([a.x, a.y], road.nativeGroundCutPolygons) ||
                  withinBridge([b.x, b.y], road.nativeGroundCutPolygons))
              )
                continue;
              if (
                !withinBridge(
                  [a.x, a.y],
                  road.nativeLaneClipPolygons ?? road.nativePolygons ?? []
                ) ||
                !withinBridge(
                  [b.x, b.y],
                  road.nativeLaneClipPolygons ?? road.nativePolygons ?? []
                ) ||
                !withinBridge(
                  [(a.x + b.x) / 2, (a.y + b.y) / 2],
                  road.nativeLaneClipPolygons ?? road.nativePolygons ?? []
                )
              )
                continue;
              beam(
                [a.x, streetHeight(terrain, [a.x, a.y], road) + 0.04, a.y],
                [b.x, streetHeight(terrain, [b.x, b.y], road) + 0.04, b.y],
                0.15,
                0.012,
                paint
              );
            }
          }
        }
      for (const path of (detail ? road.nativeRailPaths : undefined) ?? []) {
        for (const offset of [-0.7175, 0.7175]) {
          const rail = streetOffsets(path, offset);
          for (let i = 1; i < rail.length; i++) {
            const a = rail[i - 1],
              b = rail[i];
            beam(
              [a[0], streetHeight(terrain, a, road) + 0.18, a[1]],
              [b[0], streetHeight(terrain, b, road) + 0.18, b[1]],
              0.085,
              0.16,
              underside
            );
          }
        }
        for (let i = 1; i < path.length; i++) {
          const a = path[i - 1],
            b = path[i],
            length = Math.hypot(b[0] - a[0], b[1] - a[1]);
          for (let s = 0; s < length; s += 2.4) {
            const t = s / length,
              p: Point = [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
            const dx = -(b[1] - a[1]) / length,
              dy = (b[0] - a[0]) / length;
            const h = streetHeight(terrain, p, road) + 0.08;
            beam([p[0] - dx, h, p[1] - dy], [p[0] + dx, h, p[1] + dy], 0.22, 0.12, concrete);
          }
        }
      }
      ends.push(positions.length / 9);
      continue;
    }
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
