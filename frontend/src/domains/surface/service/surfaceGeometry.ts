import { Color } from 'three';
import type { SurfaceFrame, SurfaceMetric } from '../entity/surface';
import type { Terrain } from '../../terrain/entity/terrain';
import { terrainHeight } from '../../terrain/service/terrainService';
import { surfaceColor } from './surfaceService';
import { arrowTriangles, surfaceDirections } from './surfaceDirections';
export function surfaceGeometry(
  frame: SurfaceFrame,
  metric: SurfaceMetric,
  terrain: Terrain | null
) {
  const cells = frame.cells.filter((c) => c.depthM > 1e-6);
  const arrows = metric === 'speed' ? surfaceDirections(frame) : [];
  const positions: number[] = [],
    colors: number[] = [],
    flows: number[] = [];
  const depths: number[] = [],
    faces: number[] = [];
  const color = new Color();
  type Point = readonly [number, number];
  type Edge = { a: Point; b: Point; cell: SurfaceFrame['cells'][number]; floor: number };
  const edges = new Map<string, Edge>();
  const heightCache = new Map<string, number>();
  const height = (p: Point) => {
    const key = p.join('/');
    let value = heightCache.get(key);
    if (value === undefined) {
      value = terrainHeight(terrain, p) + 0.02;
      heightCache.set(key, value);
    }
    return value;
  };
  const vertex = (p: Point, depth: number, face: number, cell?: SurfaceFrame['cells'][number]) => {
    // 원 수심을 표시 지형 위의 상대 두께로만 사용하며 절대 수면고로 해석하지 않는다.
    positions.push(p[0], height(p) + depth, -p[1]);
    colors.push(color.r, color.g, color.b);
    flows.push(
      ...(cell?.flowDirection
        ? [cell.flowDirection[0] * cell.speedMps, -cell.flowDirection[1] * cell.speedMps]
        : [0, 0])
    );
    depths.push(cell?.depthM ?? 0);
    faces.push(face);
  };
  for (const cell of cells) {
    color.set(surfaceColor(cell, metric));
    const [a, b, c] = cell.vertices;
    const cross = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]);
    const points = cross < 0 ? [a, c, b] : [a, b, c];
    points.forEach((p) => vertex(p, cell.depthM, 1, cell));
    for (let i = 0; i < 3; i++) {
      const a = points[i],
        b = points[(i + 1) % 3];
      const key = [a.join('/'), b.join('/')].sort().join(':');
      const other = edges.get(key);
      if (!other) edges.set(key, { a, b, cell, floor: 0 });
      else if (other.cell.depthM === cell.depthM) edges.delete(key);
      else
        edges.set(
          key,
          cell.depthM > other.cell.depthM
            ? { a, b, cell, floor: other.cell.depthM }
            : { ...other, floor: cell.depthM }
        );
    }
  }
  for (const { a, b, cell, floor } of edges.values()) {
    color.set(surfaceColor(cell, metric));
    [
      [a, floor],
      [b, floor],
      [b, cell.depthM],
      [a, floor],
      [b, cell.depthM],
      [a, cell.depthM],
    ].forEach(([p, d]) => vertex(p as Point, d as number, 0, cell));
  }
  const byId = new Map(cells.map((cell) => [cell.triangleId, cell]));
  arrows.forEach((arrow) => {
    color.set(arrow.color);
    const cell = byId.get(arrow.triangleId)!;
    arrowTriangles.flat().forEach((index) => vertex(arrow.points[index], cell.depthM + 0.035, -1));
  });
  return {
    positions: new Float32Array(positions),
    colors: new Float32Array(colors),
    flows: new Float32Array(flows),
    depths: new Float32Array(depths),
    faces: new Float32Array(faces),
  };
}
export function surfacePlanPaths(frame: SurfaceFrame, metric: SurfaceMetric) {
  const paths = new Map<string, string[]>();
  for (const cell of frame.cells) {
    if (cell.depthM <= 1e-6) continue;
    const color = surfaceColor(cell, metric);
    const path = cell.vertices.map(([x, y], i) => `${i ? 'L' : 'M'}${x},${-y}`).join('') + 'Z';
    const group = paths.get(color) ?? [];
    group.push(path);
    paths.set(color, group);
  }
  return [...paths].map(([color, parts]) => ({ color, path: parts.join('') }));
}
