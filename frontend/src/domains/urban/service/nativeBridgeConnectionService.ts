import type { NativeBridgeGroup, ProfileConnection } from '../dto/nativeBridgeDto';
type Point = [number, number];
export function profilePointAt(coordinates: Point[], distance: number): Point {
  let walked = 0;
  for (let i = 1; i < coordinates.length; i++) {
    const a = coordinates[i - 1],
      b = coordinates[i],
      length = Math.hypot(b[0] - a[0], b[1] - a[1]);
    if (walked + length >= distance) {
      const t = Math.max(0, Math.min(1, (distance - walked) / (length || 1)));
      return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
    }
    walked += length;
  }
  return coordinates.at(-1)!;
}
export const sourceEndpointKey = (point: Point) => point.map((v) => Math.round(v * 1000)).join(',');
function project(point: Point, coordinates: Point[]) {
  let distance = Infinity,
    along = 0,
    walked = 0;
  for (let i = 1; i < coordinates.length; i++) {
    const a = coordinates[i - 1],
      b = coordinates[i],
      dx = b[0] - a[0],
      dy = b[1] - a[1];
    const length = Math.hypot(dx, dy);
    const t = Math.max(
      0,
      Math.min(1, ((point[0] - a[0]) * dx + (point[1] - a[1]) * dy) / (length * length || 1))
    );
    const d = Math.hypot(point[0] - a[0] - dx * t, point[1] - a[1] - dy * t);
    if (d < distance) {
      distance = d;
      along = walked + t * length;
    }
    walked += length;
  }
  return { distance, along, length: walked };
}
export function connectBridgeProfiles(
  groups: NativeBridgeGroup[],
  lift: (g: NativeBridgeGroup) => number
) {
  const records = groups.flatMap((group) =>
    group.profiles.filter((p) => !p.steps).map((profile) => ({ group, profile }))
  );
  const byRoad = new Map<string, typeof records>();
  const targets: { connection: ProfileConnection; profile: (typeof records)[number]['profile'] }[] =
    [];
  const vertices = new Map<string, Set<(typeof records)[number]>>();
  for (const record of records)
    for (const point of record.profile.coordinates) {
      const key = sourceEndpointKey(point);
      if (!vertices.has(key)) vertices.set(key, new Set());
      vertices.get(key)!.add(record);
    }
  for (const record of records)
    for (const id of record.profile.roadIds) {
      if (!byRoad.has(id)) byRoad.set(id, []);
      byRoad.get(id)!.push(record);
    }
  for (const { group, profile } of records) {
    const candidates = new Set([
      ...profile.roadIds.flatMap((id) => byRoad.get(id) ?? []),
      ...records.filter((r) => r.group === group),
    ]);
    const length = project(profile.coordinates[0], profile.coordinates).length;
    const connections: ProfileConnection[] = [];
    for (const side of [0, 1] as const) {
      const endpoint = side === 0 ? profile.coordinates[0] : profile.coordinates.at(-1)!;
      const extension = side === 0 ? profile.span[0] : length - profile.span[1];
      if (extension < 1) continue;
      let best: ProfileConnection | undefined;
      const junctions = vertices.get(sourceEndpointKey(endpoint)) ?? new Set();
      for (const other of new Set([...candidates, ...junctions])) {
        if (other.profile === profile || !!other.profile.rail !== !!profile.rail) continue;
        const position = project(endpoint, other.profile.coordinates);
        // 같은 원 중심선 위에서 실제로 겹치는 접속 구간만 이어 섬 위에서 상판이 급락하지 않게 한다.
        if (position.distance > 0.05) continue;
        if (
          junctions.has(other) &&
          position.along > 0.001 &&
          position.along < position.length - 0.001
        ) {
          // 원 끝점이 다른 접속 경로 중간에 합류하면 그 지점의 높이를 공유한다.
          const { connections: _connections, ...target } = other.profile;
          best = {
            side,
            gapM: extension,
            deckPolygons: other.group.displayDatumPolygons ?? other.group.polygons,
            deckLiftM: lift(other.group),
            endpointTarget: {
              ...target,
              point: endpoint,
              deckPolygons: other.group.displayDatumPolygons ?? other.group.polygons,
              deckLiftM: lift(other.group),
            },
          };
          targets.push({ connection: best, profile: other.profile });
          break;
        }
        const ownEdge = side === 0 ? profile.coordinates[1] : profile.coordinates.at(-2)!;
        const nearer = project(ownEdge, other.profile.coordinates);
        if (nearer.distance > 0.05 || Math.abs(nearer.along - position.along) < 1e-6) continue;
        // 경로 끝이 상대 상판 안까지 들어가면 침투 길이를 빼 실제 상판 간격으로 보간한다.
        const enteringStart = nearer.along < position.along;
        const toDeck = enteringStart
          ? other.profile.span[0] - position.along
          : position.along - other.profile.span[1];
        const gapM = extension + toDeck;
        if (gapM > 220 || gapM < 2) continue;
        if (!best || gapM < best.gapM)
          best = {
            side,
            gapM,
            deckPolygons: other.group.displayDatumPolygons ?? other.group.polygons,
            deckLiftM: lift(other.group),
          };
      }
      if (best) connections.push(best);
    }
    if (connections.length) profile.connections = connections;
  }
  // 연속된 합류가 앞 단계의 연결 보정을 잃지 않도록 전체 연결 그래프를 완성한다.
  for (const { connection, profile } of targets)
    connection.endpointTarget!.connections = profile.connections;
  return groups;
}
