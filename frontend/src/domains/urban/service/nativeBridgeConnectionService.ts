import type { NativeBridgeGroup, ProfileConnection } from '../dto/nativeBridgeDto';
type Point = [number, number];
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
      for (const other of candidates) {
        if (other.profile === profile || !!other.profile.rail !== !!profile.rail) continue;
        const position = project(endpoint, other.profile.coordinates);
        // 같은 원 중심선 위에서 실제로 겹치는 접속 구간만 이어 섬 위에서 상판이 급락하지 않게 한다.
        if (position.distance > 0.05) continue;
        const toDeck =
          position.along < other.profile.span[0]
            ? other.profile.span[0] - position.along
            : position.along > other.profile.span[1]
              ? position.along - other.profile.span[1]
              : 0;
        const gapM = extension + toDeck;
        if (gapM > 220 || gapM < 2) continue;
        const ownEdge = side === 0 ? profile.coordinates[1] : profile.coordinates.at(-2)!;
        const nearer = project(ownEdge, other.profile.coordinates);
        const nextToDeck =
          nearer.along < other.profile.span[0]
            ? other.profile.span[0] - nearer.along
            : nearer.along > other.profile.span[1]
              ? nearer.along - other.profile.span[1]
              : 0;
        if (nearer.distance > 0.05 || nextToDeck <= toDeck) continue;
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
  return groups;
}
