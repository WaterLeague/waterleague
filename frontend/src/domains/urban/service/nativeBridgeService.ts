import type { Terrain } from '../../terrain/entity/terrain';
import { terrainMeshHeight } from '../../terrain/service/terrainDrapeService';
import {
  connectBridgeProfiles,
  profilePointAt,
  sourceEndpointKey,
} from './nativeBridgeConnectionService';
type Polygons = [number, number][][][];
const flat = {};
const cache = new WeakMap<object, WeakMap<object, number>>();
const groupCache = new WeakMap<object, WeakMap<object, number>>();
export const nativeBridgeLiftM = 6.5;
export function connectBridgeDatums(
  groups: import('../dto/nativeBridgeDto').NativeBridgeGroup[],
  waterPolygons?: Polygons
) {
  const parents = groups.map((_, i) => i);
  const root = (i: number): number => {
    while (parents[i] !== i) {
      parents[i] = parents[parents[i]];
      i = parents[i];
    }
    return i;
  };
  const byName = new Map<string, number[]>();
  const roads = groups.map((g) => new Set(g.profiles.flatMap((p) => p.roadIds)));
  groups.forEach((g, i) => {
    for (const name of g.names ?? []) {
      if (g.kinds?.includes('지하차도')) continue;
      for (const j of byName.get(name) ?? []) {
        const sameTraffic = !!g.kinds?.includes('철교') === !!groups[j].kinds?.includes('철교');
        if (
          name === '반포대교' ||
          name === '청담대교' ||
          (sameTraffic && [...roads[i]].some((id) => roads[j].has(id)))
        )
          parents[root(i)] = root(j);
      }
      if (!byName.has(name)) byName.set(name, []);
      byName.get(name)!.push(i);
    }
  });
  const ends = new Map<string, number[]>();
  groups.forEach((g, i) => {
    if (g.kinds?.includes('지하차도')) return;
    for (const p of g.profiles.filter((p) => !p.steps))
      for (const station of p.span) {
        const key = sourceEndpointKey(profilePointAt(p.coordinates, station));
        for (const j of ends.get(key) ?? [])
          if (
            nativeDeckLift(g) === nativeDeckLift(groups[j]) &&
            !!g.kinds?.includes('철교') === !!groups[j].kinds?.includes('철교') &&
            [...roads[i]].some((id) => roads[j].has(id))
          )
            parents[root(i)] = root(j);
        if (!ends.has(key)) ends.set(key, []);
        ends.get(key)!.push(i);
      }
  });
  const datums = new Map<number, Polygons>();
  groups.forEach((g, i) => {
    const key = root(i);
    if (!datums.has(key)) datums.set(key, []);
    datums.get(key)!.push(...g.polygons);
  });
  // 같은 이름만으로 떨어진 구조를 묶지 않고 원 교통 경로의 연결을 확인한다.
  return connectBridgeProfiles(
    groups.map((group, i) => ({
      ...group,
      profiles: group.profiles.map(({ connections: _connections, ...profile }) => ({ ...profile })),
      displayDatumPolygons: datums.get(root(i))!,
      ...(waterPolygons ? { displayWaterPolygons: waterPolygons } : {}),
    })),
    nativeDeckLift
  );
}
export function nativeDeckLift(group: import('../dto/nativeBridgeDto').NativeBridgeGroup) {
  return group.names?.includes('반포대교') ||
    (group.names?.includes('청담대교') && !group.kinds?.includes('철교'))
    ? 13.5
    : nativeBridgeLiftM;
}
export function withinBridge(
  point: readonly [number, number],
  polygons: Polygons,
  tolerance = 1e-5
) {
  const inside = (ring: [number, number][]) => {
    let value = false;
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      const a = ring[i],
        b = ring[j];
      const dx = b[0] - a[0],
        dy = b[1] - a[1],
        length2 = dx * dx + dy * dy;
      const t = Math.max(
        0,
        Math.min(1, ((point[0] - a[0]) * dx + (point[1] - a[1]) * dy) / (length2 || 1))
      );
      if (Math.hypot(point[0] - a[0] - t * dx, point[1] - a[1] - t * dy) < tolerance) return true;
      if (
        a[1] > point[1] !== b[1] > point[1] &&
        point[0] < ((b[0] - a[0]) * (point[1] - a[1])) / (b[1] - a[1]) + a[0]
      )
        value = !value;
    }
    return value;
  };
  return polygons.some((p) => inside(p[0]) && !p.slice(1).some(inside));
}
export function nativeBridgeHeight(
  terrain: Terrain | null,
  polygons: Polygons,
  lift = nativeBridgeLiftM
) {
  const key = terrain ?? flat;
  let groups = groupCache.get(key);
  if (!groups) {
    groups = new WeakMap();
    groupCache.set(key, groups);
  }
  const known = groups.get(polygons);
  if (known !== undefined) return known + lift - nativeBridgeLiftM;
  let heights = cache.get(key);
  if (!heights) {
    heights = new WeakMap();
    cache.set(key, heights);
  }
  let result = -Infinity;
  for (const polygon of polygons) {
    let height = heights.get(polygon);
    if (height === undefined) {
      height = -Infinity;
      for (let i = 1; i < polygon[0].length; i++) {
        const a = polygon[0][i - 1],
          b = polygon[0][i];
        const steps = Math.max(1, Math.ceil(Math.hypot(b[0] - a[0], b[1] - a[1]) / 30));
        for (let j = 0; j <= steps; j++)
          height = Math.max(
            height,
            terrainMeshHeight(terrain, [
              a[0] + ((b[0] - a[0]) * j) / steps,
              a[1] + ((b[1] - a[1]) * j) / steps,
            ])
          );
      }
      height += nativeBridgeLiftM;
      heights.set(polygon, height);
    }
    result = Math.max(result, height);
  }
  groups.set(polygons, result);
  return result + lift - nativeBridgeLiftM;
}
type HeightStep = {
  ground: number;
  base: number;
  weight: number;
  deck: number;
  target: import('../dto/nativeBridgeDto').NativeBridgeProfile;
  point: readonly [number, number];
};
function profileHeightStep(
  terrain: Terrain | null,
  point: readonly [number, number],
  profile: import('../dto/nativeBridgeDto').NativeBridgeProfile
): number | HeightStep {
  const ground = terrainMeshHeight(terrain, point),
    deck = nativeBridgeHeight(terrain, profile.deckPolygons, profile.deckLiftM);
  let nearest = Infinity,
    along = 0,
    walked = 0;
  let projected: readonly [number, number] = point;
  for (let i = 1; i < profile.coordinates.length; i++) {
    const a = profile.coordinates[i - 1],
      b = profile.coordinates[i],
      dx = b[0] - a[0],
      dy = b[1] - a[1],
      length = Math.hypot(dx, dy),
      t = Math.max(
        0,
        Math.min(1, ((point[0] - a[0]) * dx + (point[1] - a[1]) * dy) / (length * length || 1))
      ),
      distance = (point[0] - a[0] - dx * t) ** 2 + (point[1] - a[1] - dy * t) ** 2;
    if (distance < nearest) {
      nearest = distance;
      along = walked + t * length;
      projected = [a[0] + dx * t, a[1] + dy * t];
    }
    walked += length;
  }
  // Python·JS 누적 길이의 미소 차이가 접속 끝점 전체를 지면으로 떨어뜨리지 않게 한다.
  const start = profile.span[0] < 1e-6 ? 0 : profile.span[0];
  const end = Math.abs(walked - profile.span[1]) < 1e-6 ? walked : profile.span[1];
  const connection = profile.connections?.find((c) => c.side === (along < start ? 0 : 1));
  if (connection && (along < start || along > end)) {
    const distance = along < start ? start - along : along - end;
    if (connection.endpointTarget) {
      const target = connection.endpointTarget;
      // 합류 단면의 양쪽 가장자리도 상대 도로의 같은 좌표 높이를 따른다.
      const t = Math.max(0, Math.min(1, distance / connection.gapM));
      const weight = t * t * (3 - 2 * t);
      return {
        ground,
        deck,
        base: deck * (1 - weight),
        weight,
        target,
        point: [
          target.point[0] + point[0] - projected[0],
          target.point[1] + point[1] - projected[1],
        ],
      };
    }
    const other = nativeBridgeHeight(terrain, connection.deckPolygons, connection.deckLiftM);
    return Math.max(ground, deck + (other - deck) * Math.min(1, distance / connection.gapM));
  }
  let mix =
    along < start
      ? start
        ? along / start
        : 1
      : along > end
        ? walked > end
          ? (walked - along) / (walked - end)
          : 1
        : 1;
  mix = Math.max(0, Math.min(1, mix));
  mix = mix * mix * (3 - 2 * mix);
  if (profile.steps) {
    const steps = Math.max(1, Math.ceil(walked / 0.32));
    mix = Math.min(1, Math.ceil(mix * steps) / steps);
  }
  return Math.max(ground, ground + (deck - ground) * mix);
}

export function nativeBridgeProfileHeight(
  terrain: Terrain | null,
  point: readonly [number, number],
  profile: import('../dto/nativeBridgeDto').NativeBridgeProfile
): number {
  const chain: HeightStep[] = [];
  const seen = new Map<object, Map<string, number>>();
  let current = profile,
    at = point,
    height = 0;
  for (;;) {
    const key = at.map((v) => Math.round(v * 1e6)).join(',');
    const repeated = seen.get(current)?.get(key);
    if (repeated !== undefined) {
      // 순환 진입로는 높이 식 h=max(지면,a+b*h)의 고정점으로 풀어 시작 순서에 무관하게 연결한다.
      let base = 0,
        weight = 1,
        floor = -Infinity;
      for (const step of chain.slice(repeated)) {
        floor = Math.max(floor, base + weight * step.ground);
        base += weight * step.base;
        weight *= step.weight;
      }
      height = Math.max(
        floor,
        weight < 1 - 1e-12
          ? base / (1 - weight)
          : Math.max(...chain.slice(repeated).map((s) => s.deck))
      );
      break;
    }
    if (!seen.has(current)) seen.set(current, new Map());
    seen.get(current)!.set(key, chain.length);
    const step = profileHeightStep(terrain, at, current);
    if (typeof step === 'number') {
      height = step;
      break;
    }
    chain.push(step);
    current = step.target;
    at = step.point;
  }
  for (let i = chain.length - 1; i >= 0; i--)
    height = Math.max(chain[i].ground, chain[i].base + chain[i].weight * height);
  return height;
}
