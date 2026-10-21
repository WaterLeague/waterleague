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
import { bridgeAxis } from './nativeBridgeStructureService';

type Point = readonly [number, number];
export function bridgeSurfaceSupports(groups: NativeBridgeGroup[], point: Point, onWater: boolean) {
  return groups.filter(
    (g) =>
      withinBridge(point, g.polygons) ||
      g.sidewalks?.some((s) => withinBridge(point, s.polygons)) ||
      (!onWater &&
        (g.profiles.some((p) => withinBridge(point, p.polygons)) ||
          g.sidewalks?.some((s) => s.approaches?.some((a) => withinBridge(point, a.polygons)))))
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
        !g.kinds?.includes('지하차도') &&
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
          withinBridge(point, group.polygons, 0.301) ||
          group.sidewalks?.some((s) => withinBridge(point, s.polygons, 0.301))
        )
          return nativeBridgeHeight(terrain, deckPolygons, deckLiftM);
        const profiles = [
          ...group.profiles.filter((p) => withinBridge(point, p.polygons, 0.301)),
          ...(group.sidewalks ?? [])
            .flatMap((s) =>
              (s.approaches ?? [])
                .filter((a) => withinBridge(point, a.polygons, 0.301))
                .map((a) => group.profiles[a.profileIndex])
            )
            .filter(Boolean),
        ];
        // 부속물은 같은 통행면의 상판·육상 접속 높이를 공유한다.
        return profiles.length
          ? Math.max(
              ...profiles.map((p) =>
                nativeBridgeProfileHeight(terrain, point, { ...p, deckPolygons, deckLiftM })
              )
            )
          : terrainMeshHeight(terrain, point);
      })
    );
}
export function bridgeAttachmentSupports(
  groups: NativeBridgeGroup[],
  point: Point,
  segment?: [Point, Point]
) {
  return groups
    .filter(
      (group) =>
        withinBridge(point, group.polygons, 0.301) ||
        group.profiles.some((p) => withinBridge(point, p.polygons, 0.301)) ||
        group.sidewalks?.some(
          (s) =>
            withinBridge(point, s.polygons, 0.301) ||
            s.approaches?.some((a) => withinBridge(point, a.polygons, 0.301))
        )
    )
    .filter((group) => {
      const ownedWalk = group.sidewalks?.some(
        (s) =>
          withinBridge(point, s.polygons) ||
          s.approaches?.some((a) => withinBridge(point, a.polygons))
      );
      if (!segment)
        return ownedWalk || !withinBridge(point, group.preservedUnderpassPolygons ?? []);
      const dx = segment[1][0] - segment[0][0],
        dy = segment[1][1] - segment[0][1];
      let axis = bridgeAxis(group.polygons),
        nearest = Infinity;
      for (const profile of group.profiles.filter((p) => !p.steps))
        for (let i = 1; i < profile.coordinates.length; i++) {
          const a = profile.coordinates[i - 1],
            b = profile.coordinates[i],
            x = b[0] - a[0],
            y = b[1] - a[1];
          const length = Math.hypot(x, y);
          const t = Math.max(
            0,
            Math.min(1, ((point[0] - a[0]) * x + (point[1] - a[1]) * y) / (length * length || 1))
          );
          const d = Math.hypot(point[0] - a[0] - x * t, point[1] - a[1] - y * t);
          if (d < nearest && length > 0) {
            nearest = d;
            axis = [x / length, y / length];
          }
        }
      // 겹친 평면 위치만으로 하부 도로의 횡단 난간을 상부로 끌어올리지 않는다.
      return Math.abs(dx * axis[0] + dy * axis[1]) / (Math.hypot(dx, dy) || 1) >= 0.65;
    });
}
export type NativeBridgeTransport = Map<number, NativeBridgeProfile[]> & {
  groundCuts?: NativeGroundCuts;
  attachmentCuts?: NativeGroundCuts;
  tunnelCuts?: NativeGroundCuts;
};
export function bridgeTransportBindings(groups: NativeBridgeGroup[]): NativeBridgeTransport {
  const result: NativeBridgeTransport = new Map();
  result.groundCuts = new NativeGroundCuts(groups);
  result.attachmentCuts = new NativeGroundCuts(
    groups.map((group) => ({
      ...group,
      groundCutPolygons: [],
      sourceSurfaceCuts: [],
      surfaceCuts: [
        {
          roles: ['SIDEWALK_AREA'],
          polygons: group.attachmentPolygons ?? [
            ...group.polygons,
            ...group.profiles.flatMap((p) => p.polygons),
            ...(group.sidewalks ?? []).flatMap((s) => [
              ...s.polygons,
              ...(s.approaches ?? []).flatMap((a) => a.polygons),
            ]),
          ],
        },
      ],
    })),
    [],
    false
  );
  for (const group of groups)
    if (!group.kinds?.includes('지하차도'))
      for (const profile of group.profiles) {
        const value = {
          ...profile,
          deckPolygons: group.displayDatumPolygons ?? group.polygons,
          deckLiftM:
            profile.rail && group.lowerDeck?.rail
              ? group.lowerDeck.deckLiftM
              : nativeDeckLift(group),
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
    let height = terrainMeshHeight(terrain, point);
    for (const profile of profiles) {
      let nearest = Infinity;
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
        nearest = Math.min(nearest, distance);
      }
      if (nearest <= Math.max(4, profile.displayWidthM / 2 + 0.1))
        height = Math.max(height, nativeBridgeProfileHeight(terrain, point, profile));
    }
    // 원 레코드가 같은 여러 선분에서도 교량 접속 중심선 근처만 높이를 적용한다.
    return height;
  };
}
