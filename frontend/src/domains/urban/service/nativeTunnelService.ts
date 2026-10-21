import type { NativeTransport } from '../dto/nativeTransportDto';
import type { Street } from '../entity/urban';
import type { Terrain } from '../../terrain/entity/terrain';
import { terrainMeshHeight } from '../../terrain/service/terrainDrapeService';
import { withinBridge } from './nativeBridgeService';
export type NativeTunnel = NativeTransport['tunnels'][number];
export function tunnelHeight(
  tunnel: NativeTunnel,
  point: readonly [number, number],
  terrain: Terrain | null
) {
  let nearest = Infinity,
    result = terrainMeshHeight(terrain, point);
  for (const profile of tunnel.profiles) {
    let walked = 0;
    const path = profile.coordinates;
    const length = path
      .slice(1)
      .reduce((sum, p, i) => sum + Math.hypot(p[0] - path[i][0], p[1] - path[i][1]), 0);
    for (let i = 1; i < path.length; i++) {
      const a = path[i - 1],
        b = path[i],
        dx = b[0] - a[0],
        dy = b[1] - a[1],
        segment = Math.hypot(dx, dy);
      const t = Math.max(
        0,
        Math.min(1, ((point[0] - a[0]) * dx + (point[1] - a[1]) * dy) / (segment * segment || 1))
      );
      const d = Math.hypot(point[0] - a[0] - dx * t, point[1] - a[1] - dy * t);
      if (d < nearest) {
        nearest = d;
        const along = (walked + t * segment) / (length || 1);
        // 터널 종단 표고가 없어 원 통로 양 끝의 지형 높이를 표시용으로 보간한다.
        result =
          terrainMeshHeight(terrain, path[0]) * (1 - along) +
          terrainMeshHeight(terrain, path.at(-1)!) * along;
      }
      walked += segment;
    }
  }
  return Math.min(result, terrainMeshHeight(terrain, point));
}
export function attachNativeTunnels(roads: Street[], tunnels: NativeTunnel[]): Street[] {
  const entries = tunnels.map((t) => ({
    t,
    b: t.polygons
      .flatMap((p) => p[0])
      .reduce(
        (b, p) => [
          Math.min(b[0], p[0]),
          Math.min(b[1], p[1]),
          Math.max(b[2], p[0]),
          Math.max(b[3], p[1]),
        ],
        [Infinity, Infinity, -Infinity, -Infinity]
      ),
  }));
  return roads.map((road) => {
    if (road.nativeSourceRole !== 'ROAD_CENTERLINE') return road;
    const nearby = entries
      .filter(
        ({ t, b }) =>
          road.coordinates.some((p, i) => {
            const a = road.coordinates[Math.max(0, i - 1)];
            return (
              Math.min(a[0], p[0]) <= b[2] &&
              Math.max(a[0], p[0]) >= b[0] &&
              Math.min(a[1], p[1]) <= b[3] &&
              Math.max(a[1], p[1]) >= b[1]
            );
          }) && t.profiles.some((p) => road.id.startsWith(p.roadId + ':part:'))
      )
      .map((e) => e.t);
    return nearby.length ? { ...road, nativeTunnels: nearby } : road;
  });
}
export function nativeTunnelStreets(tunnels: NativeTunnel[]): Street[] {
  return tunnels
    .filter((t) => t.profiles.length && t.polygons.length)
    .map((t) => ({
      id: t.id,
      class: 'tunnel',
      districtId: '',
      widthM: 0,
      widthSource: 'NOT_CONFIRMED',
      walk: false,
      motor: false,
      oneway: 0,
      sidewalk: '',
      bridge: false,
      coordinates: t.profiles[0].coordinates,
      nativeSourceRole: 'TUNNEL_AREA',
      nativePolygons: t.polygons,
      nativeTunnels: [t],
    }));
}
export function insideTunnel(road: Street, point: readonly [number, number]) {
  return road.nativeTunnels?.find((t) => withinBridge(point, t.polygons));
}
export function connectTunnelProfiles(tunnels: NativeTunnel[]): NativeTunnel[] {
  const networks = new Map<string, NativeTunnel[]>();
  for (const tunnel of tunnels) {
    const key = tunnel.name || tunnel.id;
    if (!networks.has(key)) networks.set(key, []);
    networks.get(key)!.push(tunnel);
  }
  return [...networks.values()].flatMap((group) => {
    const paths = new Map<string, [number, number][]>();
    const key = (p: readonly [number, number]) => p.map((v) => Math.round(v * 1000)).join(',');
    const filtered = new Map<NativeTunnel, NativeTunnel['profiles']>();
    for (const t of group) {
      let longest = 0,
        axis = [1, 0];
      for (const poly of t.polygons)
        for (let i = 1; i < poly[0].length; i++) {
          const a = poly[0][i - 1],
            b = poly[0][i],
            length = Math.hypot(b[0] - a[0], b[1] - a[1]);
          if (length > longest) {
            longest = length;
            axis = [(b[0] - a[0]) / length, (b[1] - a[1]) / length];
          }
        }
      const profiles = t.profiles.filter((p) => {
        const a = p.coordinates[0],
          b = p.coordinates.at(-1)!,
          length = Math.hypot(b[0] - a[0], b[1] - a[1]);
        return (
          length > 8 &&
          Math.abs(((b[0] - a[0]) * axis[0] + (b[1] - a[1]) * axis[1]) / length) > 0.65
        );
      });
      filtered.set(t, profiles);
      for (const p of profiles) {
        const id = [key(p.coordinates[0]), key(p.coordinates.at(-1)!)].sort().join(':');
        if (!paths.has(id)) paths.set(id, p.coordinates);
      }
    }
    const entries = [...paths.values()];
    const extended = (source: [number, number][]) => {
      let points = [...source];
      const used = new Set<string>([[key(source[0]), key(source.at(-1)!)].sort().join(':')]);
      for (const side of [0, 1])
        for (let n = 0; n < entries.length; n++) {
          const end = side === 0 ? points[0] : points.at(-1)!,
            before = side === 0 ? points[1] : points.at(-2)!;
          const matches = entries
            .filter(
              (p) =>
                !used.has([key(p[0]), key(p.at(-1)!)].sort().join(':')) &&
                (key(p[0]) === key(end) || key(p.at(-1)!) === key(end))
            )
            .map((p) => (key(p[0]) === key(end) ? p : [...p].reverse()))
            .filter((p) => {
              const dx = end[0] - before[0],
                dy = end[1] - before[1],
                ex = p[1][0] - end[0],
                ey = p[1][1] - end[1];
              return (dx * ex + dy * ey) / (Math.hypot(dx, dy) * Math.hypot(ex, ey)) > 0.7;
            });
          if (matches.length !== 1) break;
          const next = matches[0];
          used.add([key(next[0]), key(next.at(-1)!)].sort().join(':'));
          points =
            side === 0 ? [...next.slice(1).reverse(), ...points] : [...points, ...next.slice(1)];
        }
      return points;
    };
    return group.map((t) => ({
      ...t,
      profiles: filtered.get(t)!.map((p) => ({ ...p, coordinates: extended(p.coordinates) })),
    }));
  });
}
