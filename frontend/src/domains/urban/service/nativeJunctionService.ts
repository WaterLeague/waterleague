import type { Street } from '../entity/urban';
type Point = [number, number];
export function connectNativeJunctions(roads: Street[]): Street[] {
  const nodes = new Map<string, { road: Street; point: Point; side: 0 | 1 }[]>();
  for (const road of roads)
    if (road.nativeSourceRole === 'ROAD_CENTERLINE')
      for (const side of [0, 1] as const) {
        const point = side === 0 ? road.coordinates[0] : road.coordinates.at(-1)!;
        const key = point.map((v) => Math.round(v * 1000)).join(',');
        if (!nodes.has(key)) nodes.set(key, []);
        nodes.get(key)!.push({ road, point, side });
      }
  const cuts = new Map<string, Point[][][]>();
  for (const values of nodes.values()) {
    if (values.length < 2) continue;
    const vectors = values.map(({ road, point, side }) => {
      const q = side === 0 ? road.coordinates[1] : road.coordinates.at(-2)!;
      const length = Math.hypot(q[0] - point[0], q[1] - point[1]);
      return [(q[0] - point[0]) / length, (q[1] - point[1]) / length];
    });
    const junction =
      values.length > 2 ||
      Math.abs(vectors[0][0] * vectors[1][0] + vectors[0][1] * vectors[1][1]) < 0.98 ||
      values[0].road.lanes !== values[1].road.lanes;
    if (!junction) continue;
    const radius = Math.max(3, ...values.map((v) => v.road.widthM * 0.6));
    const [x, y] = values[0].point;
    const ring: Point[] = Array.from({ length: 17 }, (_, i) => [
      x + Math.cos((i * Math.PI) / 8) * radius,
      y + Math.sin((i * Math.PI) / 8) * radius,
    ]);
    // 연결 노드의 차선은 접속 폭만큼 비워 다른 방향의 직진 도색과 겹치지 않는다.
    for (const { road } of values) {
      if (!cuts.has(road.id)) cuts.set(road.id, []);
      cuts.get(road.id)!.push([ring]);
    }
  }
  return roads.map((road) =>
    cuts.has(road.id) ? { ...road, nativeJunctionPolygons: cuts.get(road.id) } : road
  );
}
