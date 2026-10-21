import type { NativeBridgeGroup, NativeBridgeProfile } from '../dto/nativeBridgeDto';
import type { Terrain } from '../../terrain/entity/terrain';
import { terrainMeshHeight } from '../../terrain/service/terrainDrapeService';
import { nativeBridgeProfileHeight, nativeDeckLift } from './nativeBridgeService';

type Point = readonly [number, number];
export type NativeBridgeTransport = Map<number, NativeBridgeProfile[]>;
export function bridgeTransportBindings(groups: NativeBridgeGroup[]): NativeBridgeTransport {
  const result: NativeBridgeTransport = new Map();
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
