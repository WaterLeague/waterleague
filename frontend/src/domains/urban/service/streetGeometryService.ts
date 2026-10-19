import { Color } from 'three';
import type { Street } from '../entity/urban';
import type { Terrain } from '../../terrain/entity/terrain';
import { drapeTriangle, terrainMeshHeight } from '../../terrain/service/terrainDrapeService';
export function streetHeight(
  terrain: Terrain | null,
  point: readonly [number, number],
  bridge: boolean
) {
  // 도로의 표시 오프셋이 얕은 침수 수면(지형+0.02m)을 가리지 않도록 한다.
  return terrainMeshHeight(terrain, point) + (bridge ? 3 : 0.004);
}
export function streetGeometry(roads: Street[], terrain: Terrain | null, detail: boolean) {
  const positions: number[] = [],
    colors: number[] = [];
  const asphalt = new Color('#667071'),
    walk = new Color('#b3ae9f'),
    sidewalk = new Color('#a6a698'),
    paint = new Color('#e2d8aa');
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
    let along = 0;
    for (let i = 1; i < road.coordinates.length; i++) {
      const a = road.coordinates[i - 1],
        b = road.coordinates[i],
        length = Math.hypot(b[0] - a[0], b[1] - a[1]);
      if (detail && road.motor && road.sidewalk !== 'no' && !/motorway|trunk/.test(road.class))
        quad(a, b, road.widthM + 2.8, sidewalk, road.bridge);
      quad(a, b, road.widthM, road.walk ? walk : asphalt, road.bridge, 0.004);
      if (detail && road.motor && road.widthM >= 7) {
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
  }
  return { positions: new Float32Array(positions), colors: new Float32Array(colors) };
}
