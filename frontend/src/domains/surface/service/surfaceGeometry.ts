import { Color } from 'three';
import type { SurfaceFrame, SurfaceMetric } from '../entity/surface';
import type { Terrain } from '../../terrain/entity/terrain';
import { terrainHeight } from '../../terrain/service/terrainService';
import { surfaceColor } from './surfaceService';
export function surfaceGeometry(
  frame: SurfaceFrame,
  metric: SurfaceMetric,
  terrain: Terrain | null
) {
  const cells = frame.cells.filter((c) => c.depthM > 1e-6);
  const positions = new Float32Array(cells.length * 9),
    colors = new Float32Array(cells.length * 9);
  const color = new Color();
  cells.forEach((cell, i) => {
    color.set(surfaceColor(cell, metric));
    cell.vertices.forEach((p, j) => {
      // 표시 지표에 색상만 올리며 원 계산 수심을 수면 표고로 바꾸지 않는다.
      positions.set([p[0], terrainHeight(terrain, p) + 0.4, -p[1]], i * 9 + j * 3);
      colors.set([color.r, color.g, color.b], i * 9 + j * 3);
    });
  });
  return { positions, colors };
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
