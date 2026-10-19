import { Color } from 'three';
import type { Street } from '../entity/urban';
import type { Terrain } from '../../terrain/entity/terrain';
import { drapeTriangle, terrainMeshHeight } from '../../terrain/service/terrainDrapeService';
// 실측 교량 높이가 없는 공개 중심선의 층 구분용 표시 제원이다.
export const bridgeDeckHeight = 6.5;
export const bridgeDeckThickness = 0.65;
export function streetHeight(
  terrain: Terrain | null,
  point: readonly [number, number],
  bridge: boolean
) {
  // 도로의 표시 오프셋이 얕은 침수 수면(지형+0.02m)을 가리지 않도록 한다.
  return terrainMeshHeight(terrain, point) + (bridge ? bridgeDeckHeight : 0.004);
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
    sidewalk = new Color('#a6a698'),
    paint = new Color('#e2d8aa'),
    concrete = new Color('#8c989c'),
    barrier = new Color('#bdc6c7'),
    underside = new Color('#58656d'),
    aisle = new Color('#747b76');
  const aisleIds = new Set(parkingAisles);
  const face = (a: number[], b: number[], c: number[], color: Color) => {
    for (const point of [a, b, c]) {
      positions.push(point[0], point[1], -point[2]);
      colors.push(color.r, color.g, color.b);
    }
  };
  const wall = (
    a: [number, number],
    b: [number, number],
    bottom: number,
    top: number,
    color: Color
  ) => {
    const h1 = streetHeight(terrain, a, true),
      h2 = streetHeight(terrain, b, true);
    const lo1 = [a[0], h1 + bottom, a[1]],
      lo2 = [b[0], h2 + bottom, b[1]],
      hi1 = [a[0], h1 + top, a[1]],
      hi2 = [b[0], h2 + top, b[1]];
    face(lo1, lo2, hi1, color);
    face(lo2, hi2, hi1, color);
  };
  const quad = (
    a: [number, number],
    b: [number, number],
    width: number,
    color: Color,
    bridge: boolean,
    lift = 0
  ) => {
    const dx = b[0] - a[0],
      dy = b[1] - a[1],
      length = Math.hypot(dx, dy);
    if (length < 0.05) return;
    const nx = ((-dy / length) * width) / 2,
      ny = ((dx / length) * width) / 2;
    const points: [[number, number], [number, number], [number, number], [number, number]] = [
      [a[0] + nx, a[1] + ny],
      [a[0] - nx, a[1] - ny],
      [b[0] + nx, b[1] + ny],
      [b[0] - nx, b[1] - ny],
    ];
    for (const tri of [
      [points[0], points[1], points[2]],
      [points[2], points[1], points[3]],
    ] as const)
      drapeTriangle(tri, terrain, (t) => {
        for (const p of t) {
          positions.push(p[0], streetHeight(terrain, p, bridge) + lift, -p[1]);
          colors.push(color.r, color.g, color.b);
        }
      });
  };
  for (const road of roads) {
    const parking = aisleIds.has(road.id);
    let along = 0;
    for (let i = 1; i < road.coordinates.length; i++) {
      const a = road.coordinates[i - 1],
        b = road.coordinates[i],
        length = Math.hypot(b[0] - a[0], b[1] - a[1]);
      if (
        detail &&
        !parking &&
        road.motor &&
        road.sidewalk !== 'no' &&
        !/motorway|trunk/.test(road.class)
      )
        quad(a, b, road.widthM + 2.8, sidewalk, road.bridge);
      quad(a, b, road.widthM, road.walk ? walk : parking ? aisle : asphalt, road.bridge, 0.004);
      if (detail && road.bridge && length > 0.05) {
        quad(a, b, road.widthM, underside, true, -bridgeDeckThickness);
        const nx = -(b[1] - a[1]) / length,
          ny = (b[0] - a[0]) / length;
        for (const side of [-1, 1]) {
          const offset = (point: [number, number], distance: number): [number, number] => [
            point[0] + nx * distance * side,
            point[1] + ny * distance * side,
          ];
          const edgeA = offset(a, road.widthM / 2),
            edgeB = offset(b, road.widthM / 2);
          wall(edgeA, edgeB, -bridgeDeckThickness, 0.004, concrete);
          wall(edgeA, edgeB, 0.004, 0.9, barrier);
          const innerA = offset(a, road.widthM / 2 - 0.22),
            innerB = offset(b, road.widthM / 2 - 0.22);
          wall(innerA, innerB, 0.004, 0.9, barrier);
          quad(
            offset(a, road.widthM / 2 - 0.11),
            offset(b, road.widthM / 2 - 0.11),
            0.22,
            barrier,
            true,
            0.9
          );
        }
      }
      if (detail && !parking && road.motor && road.widthM >= 7) {
        for (let s = Math.ceil(along / 12) * 12; s < along + length; s += 12) {
          const start = Math.max(0, s - along),
            end = Math.min(length, start + 4);
          if (end <= start) continue;
          const point = (t: number): [number, number] => [
            a[0] + ((b[0] - a[0]) * t) / length,
            a[1] + ((b[1] - a[1]) * t) / length,
          ];
          quad(point(start), point(end), 0.2, paint, road.bridge, 0.008);
        }
      }
      along += length;
      if (positions.length > 12000000) throw new Error('도로 표시 형상 상한 초과');
    }
    ends.push(positions.length / 9);
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
