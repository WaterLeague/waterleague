import type { SurfaceFrame } from '../entity/surface';

export const maximumDirectionGlyphs = 512;
export const arrowTriangles = [
  [0, 1, 2],
  [0, 2, 3],
  [4, 5, 6],
] as const;

export function surfaceDirections(frame: SurfaceFrame) {
  const candidates = frame.cells.filter(
    (c) => c.flowDirection && c.depthM > 1e-6 && c.speedMps > 0
  );
  if (!candidates.length) return [];
  const centers = candidates.map((cell) => ({
    cell,
    center: [
      cell.vertices.reduce((s, p) => s + p[0], 0) / 3,
      cell.vertices.reduce((s, p) => s + p[1], 0) / 3,
    ] as [number, number],
  }));
  const x = centers.map((c) => c.center[0]),
    y = centers.map((c) => c.center[1]);
  const spacing = Math.max(
    1,
    Math.max(Math.max(...x) - Math.min(...x), Math.max(...y) - Math.min(...y)) / 22
  );
  const occupied = new Set<string>();
  const result: { triangleId: number; points: [number, number][]; color: string }[] = [];
  for (const { cell, center } of centers.sort((a, b) => a.cell.triangleId - b.cell.triangleId)) {
    const key = `${Math.floor(center[0] / spacing)}/${Math.floor(center[1] / spacing)}`;
    if (occupied.has(key) || result.length >= maximumDirectionGlyphs) continue;
    const [a, b, c] = cell.vertices;
    const cross = Math.abs((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]));
    const edge = Math.max(
      ...[
        [a, b],
        [b, c],
        [c, a],
      ].map(([p, q]) => Math.hypot(p[0] - q[0], p[1] - q[1]))
    );
    const length = Math.min(30, (1.8 * cross) / (3 * edge));
    if (!Number.isFinite(length) || length <= 0) continue;
    occupied.add(key);
    const [dx, dy] = cell.flowDirection!;
    // 원 격자 방향만 선택하며 화살표 길이로 속력이나 새 유동장을 만들지 않는다.
    const points = [
      [-0.5, -0.07],
      [0.12, -0.07],
      [0.12, 0.07],
      [-0.5, 0.07],
      [0.05, -0.22],
      [0.5, 0],
      [0.05, 0.22],
    ].map(([along, side]): [number, number] => [
      center[0] + length * (along * dx - side * dy),
      center[1] + length * (along * dy + side * dx),
    ]);
    result.push({
      triangleId: cell.triangleId,
      points,
      color: cell.speedMps >= 0.5 ? '#f8fafc' : '#164e63',
    });
  }
  return result;
}

export function surfaceDirectionPaths(frame: SurfaceFrame) {
  return surfaceDirections(frame).map(({ triangleId, points, color }) => ({
    triangleId,
    color,
    path: arrowTriangles
      .map(
        (indices) =>
          indices.map((i, j) => `${j ? 'L' : 'M'}${points[i][0]},${-points[i][1]}`).join('') + 'Z'
      )
      .join(''),
  }));
}
