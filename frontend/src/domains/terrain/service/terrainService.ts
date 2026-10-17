import type { Terrain } from '../entity/terrain';
export function terrainHeight(
  terrain: Terrain | null | undefined,
  point: readonly [number, number]
): number {
  if (!terrain) return 0;
  const x = Math.min(
    terrain.width - 1,
    Math.max(0, (point[0] - terrain.origin[0]) / terrain.spacing[0])
  );
  const y = Math.min(
    terrain.height - 1,
    Math.max(0, (point[1] - terrain.origin[1]) / terrain.spacing[1])
  );
  const col = Math.floor(x),
    row = Math.floor(y),
    nextCol = Math.min(col + 1, terrain.width - 1),
    nextRow = Math.min(row + 1, terrain.height - 1);
  const at = (r: number, c: number) => terrain.heights[r * terrain.width + c];
  const a = at(row, col) * (1 - x + col) + at(row, nextCol) * (x - col);
  const b = at(nextRow, col) * (1 - x + col) + at(nextRow, nextCol) * (x - col);
  return a * (1 - y + row) + b * (y - row);
}
export function terrainLine(
  terrain: Terrain | null,
  points: readonly [number, number][],
  offset: number
): number[] {
  const values: number[] = [];
  for (let i = 1; i < points.length; i++) {
    const a = points[i - 1],
      b = points[i],
      segments = Math.max(1, Math.ceil(Math.hypot(b[0] - a[0], b[1] - a[1]) / 90));
    for (let j = 0; j < segments; j++)
      for (const t of [j / segments, (j + 1) / segments]) {
        const p: [number, number] = [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
        values.push(p[0], terrainHeight(terrain, p) + offset, -p[1]);
      }
  }
  return values;
}
