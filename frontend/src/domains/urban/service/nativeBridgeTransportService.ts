import type { NativeBridgeGroup, NativeBridgeProfile } from '../dto/nativeBridgeDto';
import type { Terrain } from '../../terrain/entity/terrain';
import { terrainMeshHeight } from '../../terrain/service/terrainDrapeService';
import {
  nativeBridgeHeight,
  nativeBridgeProfileHeight,
  nativeDeckLift,
  withinBridge,
} from './nativeBridgeService';
import { NativeGroundCuts } from './nativeGroundCutService';
import type { Street } from '../entity/urban';

type Point = readonly [number, number];
export function bridgeWaterSupports(groups: NativeBridgeGroup[], point: Point) {
  return groups.filter(
    (g) =>
      withinBridge(point, g.polygons) || g.sidewalks?.some((s) => withinBridge(point, s.polygons))
  );
}
export function waterDeckBindings(
  groups: NativeBridgeGroup[],
  coordinates: [number, number][]
): Street['nativeWaterDecks'] {
  const bounds = coordinates.reduce(
    (b, p) => [
      Math.min(b[0], p[0]),
      Math.min(b[1], p[1]),
      Math.max(b[2], p[0]),
      Math.max(b[3], p[1]),
    ],
    [Infinity, Infinity, -Infinity, -Infinity]
  );
  return groups
    .filter(
      (g) =>
        g.groundCutPolygons &&
        g.bounds[0] <= bounds[2] &&
        g.bounds[2] >= bounds[0] &&
        g.bounds[1] <= bounds[3] &&
        g.bounds[3] >= bounds[1]
    )
    .map((g) => ({
      polygons: g.polygons,
      waterPolygons: g.groundCutPolygons!,
      deckPolygons: g.displayDatumPolygons ?? g.polygons,
      deckLiftM: nativeDeckLift(g),
    }));
}
export function bridgeAttachmentHeight(groups: NativeBridgeGroup[], terrain: Terrain | null) {
  return (point: Point) =>
    Math.max(
      terrainMeshHeight(terrain, point),
      ...groups.map((group) => {
        const deckPolygons = group.displayDatumPolygons ?? group.polygons;
        const deckLiftM = nativeDeckLift(group);
        if (
          withinBridge(point, group.polygons) ||
          group.sidewalks?.some((s) => withinBridge(point, s.polygons))
        )
          return nativeBridgeHeight(terrain, deckPolygons, deckLiftM);
        const profiles = group.profiles.filter((p) => withinBridge(point, p.polygons));
        // 층 속성이 없는 원 부속물은 수면과 겹치는 교량·접속 면 위에 한 번만 배치한다.
        return profiles.length
          ? Math.max(
              ...profiles.map((p) =>
                nativeBridgeProfileHeight(terrain, point, { ...p, deckPolygons, deckLiftM })
              )
            )
          : nativeBridgeHeight(terrain, deckPolygons, deckLiftM);
      })
    );
}
export type NativeBridgeTransport = Map<number, NativeBridgeProfile[]> & {
  groundCuts?: NativeGroundCuts;
};
export function bridgeTransportBindings(groups: NativeBridgeGroup[]): NativeBridgeTransport {
  const result: NativeBridgeTransport = new Map();
  result.groundCuts = new NativeGroundCuts(groups);
  for (const group of groups)
    for (const profile of group.profiles) {
      const value = {
        ...profile,
        deckPolygons: group.displayDatumPolygons ?? group.polygons,
        deckLiftM: nativeDeckLift(group),
      };
      for (const fid of profile.sourceFids ?? []) {
        if (!result.has(fid)) result.set(fid, []);
        result.get(fid)!.push(value);
      }
    }
  return result;
}
export function bridgeTransportHeight(
  profiles: NativeBridgeProfile[] | undefined,
  terrain: Terrain | null
): ((point: Point) => number) | undefined {
  if (!profiles?.length) return undefined;
  return (point) => {
    let best: NativeBridgeProfile | undefined,
      nearest = Infinity;
    for (const profile of profiles)
      for (let i = 1; i < profile.coordinates.length; i++) {
        const a = profile.coordinates[i - 1],
          b = profile.coordinates[i];
        const dx = b[0] - a[0],
          dy = b[1] - a[1];
        const t = Math.max(
          0,
          Math.min(1, ((point[0] - a[0]) * dx + (point[1] - a[1]) * dy) / (dx * dx + dy * dy || 1))
        );
        const distance = Math.hypot(point[0] - a[0] - t * dx, point[1] - a[1] - t * dy);
        if (distance < nearest) {
          nearest = distance;
          best = profile;
        }
      }
    // 원 레코드가 같은 여러 선분에서도 교량 접속 중심선 근처만 높이를 적용한다.
    return best && nearest <= 4
      ? nativeBridgeProfileHeight(terrain, point, best)
      : terrainMeshHeight(terrain, point);
  };
}
