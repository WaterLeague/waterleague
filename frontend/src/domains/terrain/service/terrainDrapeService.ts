import type { Terrain } from '../entity/terrain';

type Point = readonly [number, number];
type Triangle = readonly [Point, Point, Point];
const EPSILON = 1e-9;

// 표시 지형의 대각선과 같은 삼각면을 사용해 얕은 수면이 지형 아래로 사라지는 것을 막는다.
export function terrainMeshHeight(terrain: Terrain | null, [x, y]: Point): number {
  if (!terrain) return 0;
  const u = Math.max(0, Math.min(terrain.width - 1, (x - terrain.origin[0]) / terrain.spacing[0]));
  const v = Math.max(0, Math.min(terrain.height - 1, (y - terrain.origin[1]) / terrain.spacing[1]));
  const col = Math.min(terrain.width - 2, Math.floor(u));
  const row = Math.min(terrain.height - 2, Math.floor(v));
  const a = terrain.heights[row * terrain.width + col];
  const b = terrain.heights[row * terrain.width + col + 1];
  const c = terrain.heights[(row + 1) * terrain.width + col];
  const d = terrain.heights[(row + 1) * terrain.width + col + 1];
  const tx = u - col,
    ty = v - row;
  return tx + ty <= 1
    ? a + (b - a) * tx + (c - a) * ty
    : d + (c - d) * (1 - tx) + (b - d) * (1 - ty);
}
function clip(points: Point[], distance: (point: Point) => number): Point[] {
  const out: Point[] = [];
  for (let i = 0; i < points.length; i++) {
    const a = points[i],
      b = points[(i + 1) % points.length];
    const da = distance(a),
      db = distance(b);
    if (da >= -EPSILON) out.push(a);
    if ((da < -EPSILON && db > EPSILON) || (da > EPSILON && db < -EPSILON)) {
      const t = da / (da - db);
      out.push([a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t]);
    }
  }
  return out;
}
export function drapeTriangle(
  triangle: Triangle,
  terrain: Terrain | null,
  emit: (triangle: Triangle) => void
) {
  if (!terrain) {
    emit(triangle);
    return;
  }
  const grid = triangle.map(([x, y]): Point => [
    (x - terrain.origin[0]) / terrain.spacing[0],
    (y - terrain.origin[1]) / terrain.spacing[1],
  ]);
  const minRow = Math.max(
    -1,
    Math.min(terrain.height - 1, Math.floor(Math.min(...grid.map((p) => p[1]))))
  );
  const maxRow = Math.max(
    -1,
    Math.min(terrain.height - 1, Math.floor(Math.max(...grid.map((p) => p[1]))))
  );
  // 행을 먼저 자르면 긴 사선 도형의 빈 격자까지 순회하지 않는다.
  for (let row = minRow; row <= maxRow; row++) {
    let strip = row === -1 ? grid : clip(grid, (p) => p[1] - row);
    if (row < terrain.height - 1) strip = clip(strip, (p) => row + 1 - p[1]);
    if (strip.length < 3) continue;
    const minCol = Math.max(
      -1,
      Math.min(terrain.width - 1, Math.floor(Math.min(...strip.map((p) => p[0]))))
    );
    const maxCol = Math.max(
      -1,
      Math.min(terrain.width - 1, Math.floor(Math.max(...strip.map((p) => p[0]))))
    );
    for (let col = minCol; col <= maxCol; col++) {
      let cell = col === -1 ? strip : clip(strip, (p) => p[0] - col);
      if (col < terrain.width - 1) cell = clip(cell, (p) => col + 1 - p[0]);
      const outside = row < 0 || col < 0 || row === terrain.height - 1 || col === terrain.width - 1;
      const halves = outside
        ? [cell]
        : [1, -1].map((sign) => clip(cell, (p) => sign * (1 - (p[0] - col) - (p[1] - row))));
      for (const half of halves) {
        for (let i = 1; i + 1 < half.length; i++) {
          const points = [half[0], half[i], half[i + 1]];
          const [a, b, c] = points;
          if (Math.abs((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])) < EPSILON)
            continue;
          emit(
            points.map(([u, v]) => [
              terrain.origin[0] + u * terrain.spacing[0],
              terrain.origin[1] + v * terrain.spacing[1],
            ]) as unknown as Triangle
          );
        }
      }
    }
  }
}

export function drapeSegment(a: Point, b: Point, terrain: Terrain | null): [Point, Point][] {
  if (!terrain) return [[a, b]];
  const u = (p: Point) => (p[0] - terrain.origin[0]) / terrain.spacing[0];
  const v = (p: Point) => (p[1] - terrain.origin[1]) / terrain.spacing[1];
  const at = (t: number): Point => [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
  const cuts = new Set([0, 1]);
  for (const [start, end, count] of [
    [u(a), u(b), terrain.width],
    [v(a), v(b), terrain.height],
  ]) {
    if (Math.abs(end - start) < EPSILON) continue;
    for (
      let i = Math.max(0, Math.ceil(Math.min(start, end)));
      i <= Math.min(count - 1, Math.floor(Math.max(start, end)));
      i++
    ) {
      const t = (i - start) / (end - start);
      if (t > EPSILON && t < 1 - EPSILON) cuts.add(t);
    }
  }
  const gridCuts = [...cuts].sort((x, y) => x - y);
  for (let i = 0; i + 1 < gridCuts.length; i++) {
    const from = gridCuts[i],
      until = gridCuts[i + 1];
    const middle = at((from + until) / 2);
    if (
      u(middle) < 0 ||
      v(middle) < 0 ||
      u(middle) >= terrain.width - 1 ||
      v(middle) >= terrain.height - 1
    )
      continue;
    const col = Math.min(terrain.width - 2, Math.max(0, Math.floor(u(middle))));
    const row = Math.min(terrain.height - 2, Math.max(0, Math.floor(v(middle))));
    const diagonal = (t: number) => u(at(t)) + v(at(t)) - col - row - 1;
    const da = diagonal(from),
      db = diagonal(until);
    if (da * db < -EPSILON) cuts.add(from + ((until - from) * da) / (da - db));
  }
  const all = [...cuts].sort((x, y) => x - y);
  return all.slice(0, -1).map((t, i) => [at(t), at(all[i + 1])]);
}

export function terrainMeshContains(terrain: Terrain | null, [x, y]: Point): boolean {
  if (!terrain || !terrain.districts.length) return true;
  const col = Math.floor((x - terrain.origin[0]) / terrain.spacing[0]),
    row = Math.floor((y - terrain.origin[1]) / terrain.spacing[1]);
  if (col < 0 || row < 0 || col >= terrain.width - 1 || row >= terrain.height - 1) return false;
  const i = row * terrain.width + col;
  return [i, i + 1, i + terrain.width, i + terrain.width + 1].some((n) => terrain.districts[n] > 0);
}
